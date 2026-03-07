"""handlers/agent.py — Multi-step autonomous agent handler (F3)."""
import sys

from ..config import load_config
from ..role import get_role
from ..printer import print_error, print_info, print_success, print_warning
from ..providers.pipeline import ProviderPipeline, ProviderExhaustedError
from ..tools.builtin.shell import execute_command, is_high_risk
from ..image_utils import build_multimodal_content, is_multimodal


_PLAN_SYSTEM = """You are an autonomous agent that completes multi-step tasks using shell commands.

Given a task, respond with a numbered plan of shell commands to execute it.
Format your response EXACTLY as:

PLAN:
1. <description>
   CMD: <shell command>
2. <description>
   CMD: <shell command>
...

Rules:
- Each step must have a description and a CMD line
- Commands must be single-line shell commands
- Be conservative — prefer safe, reversible commands
- If a step has no shell command needed, use CMD: echo "done"
- Maximum 10 steps
"""

_OBSERVE_SYSTEM = """You are an autonomous agent observing command output to decide next action.

Given the original task, the plan, the command that ran, and its output, respond with ONLY a JSON object — no markdown, no explanation, no backticks.

Valid responses:
{"action": "continue"}
{"action": "retry", "command": "<corrected shell command>"}
{"action": "stop", "reason": "<why task cannot be completed safely>"}
{"action": "done"}

Rules:
- Output ONLY the JSON object, nothing else
- "action" must be one of: continue, retry, stop, done
- "retry" requires a "command" field with the corrected command
- "stop" requires a "reason" field explaining why
"""


async def _agent(task: str, model: str | None, dry_run: bool, yes: bool, images: list | None = None):
    config = load_config()

    try:
        pipeline = ProviderPipeline(
            provider_chain=config["provider_chain"],
            cooldown_seconds=config["cooldown_seconds"],
            max_retries_per_provider=config["max_retries_per_provider"],
        )
    except ProviderExhaustedError as e:
        print_error(str(e))
        sys.exit(1)

    if images:
        print_info(f"Agent task: {task} [{len(images)} image(s) attached]")
    else:
        print_info(f"Agent task: {task}")
    print_info("Generating plan...\n")

    # ── Step 1: Generate plan ─────────────────────────────────────────────────
    # Build initial plan content — multimodal if images provided
    requires_vision = bool(images)
    if images:
        plan_user_content = build_multimodal_content(f"Task: {task}", list(images))
    else:
        plan_user_content = f"Task: {task}"

    plan_messages = [
        {"role": "system", "content": _PLAN_SYSTEM},
        {"role": "user", "content": plan_user_content},
    ]

    try:
        chunks = []
        async for chunk in pipeline.stream(plan_messages, model=model, requires_vision=requires_vision):
            chunks.append(chunk)
            print(chunk, end="", flush=True)
        print("\n")
        plan_text = "".join(chunks)
    except ProviderExhaustedError as e:
        print_error(f"Failed to generate plan: {e}")
        return

    # ── Step 2: Parse plan ────────────────────────────────────────────────────
    steps = _parse_plan(plan_text)

    if not steps:
        print_error("Could not parse a valid plan from the response.")
        return

    print_info(f"Plan has {len(steps)} step(s).")

    if dry_run:
        print_info("Dry run — no commands will be executed.\n")
        for i, (desc, cmd) in enumerate(steps, 1):
            print(f"  \033[1m{i}. {desc}\033[0m")
            print(f"     \033[90m$ {cmd}\033[0m\n")
        return

    # ── Step 3: Execute plan step by step ────────────────────────────────────
    completed = []
    i = 0
    while i < len(steps):
        desc, cmd = steps[i]
        step_num = i + 1

        print(f"\033[1m── Step {step_num}/{len(steps)}: {desc}\033[0m")
        print(f"\033[90m$ {cmd}\033[0m")

        # High-risk check
        if is_high_risk(cmd):
            print_warning(f"High-risk command detected: {cmd}")
            if not yes:
                confirm = input("Execute anyway? [y/N] ").strip().lower()
                if confirm != "y":
                    print_info("Skipping step.")
                    i += 1
                    continue

        # Confirm before each step (unless --yes)
        if not yes:
            confirm = input(f"Execute? [Y/n/s(skip)/q(quit)] ").strip().lower()
            if confirm == "q":
                print_info("Agent stopped by user.")
                break
            elif confirm == "s":
                print_info("Step skipped.")
                i += 1
                continue
            elif confirm == "n":
                print_info("Agent stopped by user.")
                break

        # Execute
        exit_code, stdout, stderr = execute_command(cmd)
        output = stdout + stderr

        if stdout.strip():
            print(f"\033[32m{stdout.strip()}\033[0m")
        if stderr.strip():
            print(f"\033[33m{stderr.strip()}\033[0m")

        # ── Step 4: Observe result ────────────────────────────────────────────
        observe_text = (
            f"Task: {task}\n\n"
            f"Step {step_num}: {desc}\n"
            f"Command: {cmd}\n"
            f"Exit code: {exit_code}\n"
            f"Output:\n{output[:2000]}"  # cap output sent to AI
        )
        # Include original images in observer so it can visually verify results
        if images:
            observe_user_content = build_multimodal_content(observe_text, list(images))
        else:
            observe_user_content = observe_text

        observe_messages = [
            {"role": "system", "content": _OBSERVE_SYSTEM},
            {"role": "user", "content": observe_user_content},
        ]

        try:
            obs_chunks = []
            async for chunk in pipeline.stream(observe_messages, model=model, requires_vision=requires_vision):
                obs_chunks.append(chunk)
            observation_raw = "".join(obs_chunks).strip()
        except ProviderExhaustedError:
            observation_raw = '{"action": "continue"}'  # assume success if observation fails

        # Parse structured JSON observation (TD-7)
        import json as _json
        try:
            # Strip accidental markdown fences if model wraps in ```json
            clean = observation_raw.strip().lstrip("```json").lstrip("```").rstrip("```").strip()
            obs = _json.loads(clean)
        except (_json.JSONDecodeError, ValueError):
            # Fallback: if model ignores instructions and returns old format, try string-match
            obs = _parse_observation_fallback(observation_raw)

        action = obs.get("action", "continue").lower()
        print(f"\033[90m[agent] {obs}\033[0m\n")

        if action == "retry":
            corrected = obs.get("command", "").strip()
            if corrected:
                print_info(f"Retrying with: {corrected}")
                steps[i] = (desc, corrected)
                continue  # retry same step with corrected command
            else:
                # Malformed retry — just continue
                completed.append((desc, cmd, exit_code))
                i += 1

        elif action == "stop":
            reason = obs.get("reason", "unknown reason")
            print_error(f"Agent stopped: {reason}")
            break

        elif action == "done":
            print_success("Task complete.")
            break

        else:  # "continue" or anything unrecognised
            completed.append((desc, cmd, exit_code))
            i += 1

    print_success(f"Agent finished. {len(completed)}/{len(steps)} steps completed.")


def _parse_plan(text: str) -> list[tuple[str, str]]:
    """Parse PLAN: block into list of (description, command) tuples."""
    steps = []
    lines = text.splitlines()

    in_plan = False
    current_desc = None

    for line in lines:
        stripped = line.strip()

        if stripped.upper().startswith("PLAN:"):
            in_plan = True
            continue

        if not in_plan:
            continue

        # Match numbered step: "1. Description" or "1) Description"
        import re
        step_match = re.match(r"^\d+[.)]\s+(.+)$", stripped)
        if step_match:
            current_desc = step_match.group(1).strip()
            continue

        # Match CMD line
        if stripped.upper().startswith("CMD:") and current_desc:
            cmd = stripped[4:].strip()
            if cmd:
                steps.append((current_desc, cmd))
                current_desc = None

    return steps


def _parse_observation_fallback(text: str) -> dict:
    """Fallback parser for models that ignore JSON instructions and return old format.
    Converts legacy string responses to the structured dict format."""
    t = text.strip().upper()
    if t.startswith("RETRY:"):
        return {"action": "retry", "command": text[6:].strip()}
    elif t.startswith("STOP:"):
        return {"action": "stop", "reason": text[5:].strip()}
    elif t.startswith("DONE"):
        return {"action": "done"}
    else:
        return {"action": "continue"}
