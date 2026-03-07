"""
role.py — Role definitions for aicli.
Each role sets the system prompt and allow_tools flag.
allow_tools=False mirrors sgpt's functions=None for Shell/Code/Describe roles.
"""
from dataclasses import dataclass


@dataclass
class Role:
    name: str
    system_prompt: str
    allow_tools: bool = False


ROLES: dict[str, Role] = {
    "default": Role(
        name="default",
        system_prompt=(
            "You are a helpful, concise assistant. "
            "Provide clear, accurate answers. Use markdown when helpful."
        ),
        allow_tools=False,
    ),
    "shell": Role(
        name="shell",
        system_prompt=(
            "You are a shell command assistant. "
            "Respond with ONLY the shell command(s) needed to accomplish the task. "
            "No explanations, no markdown, no code blocks — just the raw command(s). "
            "One command per line. "
            "Prefer robust commands: use find over ls globs "
            "to avoid glob expansion failures when no files match."
        ),
        allow_tools=False,
    ),
    "code": Role(
        name="code",
        system_prompt=(
            "You are a code assistant. "
            "Respond with ONLY the code. No explanations unless explicitly asked. "
            "Do not wrap in markdown fences unless the user asks for a file."
        ),
        allow_tools=False,
    ),
    "describe": Role(
        name="describe",
        system_prompt=(
            "You are a shell command explainer. "
            "The user will give you a shell command. "
            "Explain what it does in plain English, step by step. "
            "Be concise. Flag any dangerous operations."
        ),
        allow_tools=False,
    ),
}


def get_role(name: str) -> Role:
    return ROLES.get(name, ROLES["default"])
