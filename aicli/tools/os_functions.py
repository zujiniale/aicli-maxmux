"""
aicli/tools/os_functions.py — Built-in OS Tool Implementations

These are the functions the LLM can call when the user asks for things like:
  "play music and open hacker news"
  "send email to alice@example.com saying hi"
  "summarize /tmp/docs/report.txt"
  "copy this to clipboard"

All functions are registered via @os_tool and live in TOOL_REGISTRY.
Import this module to ensure all tools are registered:

    import aicli.tools.os_functions  # noqa: F401 — side-effect registration

Security model:
  - File reads: capped at MAX_FILE_BYTES (50 KB) to prevent prompt injection
  - File writes: user must confirm, path must be inside home dir or cwd
  - Email: uses system `mail` command OR configured SMTP — never sends without confirm
  - Shell commands: never executed by tools here; use aicli cmd --run for that
  - Every write/action is logged to AUDIT_LOG

Better than ShellGPT:
  - ShellGPT fires @FunctionCall with no confirmation, no audit, no size limits
  - aicli requires explicit [Y/n] confirmation (skippable with --auto-confirm)
  - Every action logged with timestamp, args, and user decision
  - Path injection attack surface minimised (size cap + home dir guard)
"""

from __future__ import annotations
import os
import re
import sys
import asyncio
from pathlib import Path

from .registry import os_tool

# ── Constants ─────────────────────────────────────────────────────────────────
MAX_FILE_BYTES = 50 * 1024   # 50 KB — prevent prompt injection via huge files
MAX_WRITE_BYTES = 1 * 1024 * 1024  # 1 MB — reasonable write limit


# ── 1. Open URL in browser ────────────────────────────────────────────────────

@os_tool(
    name="open_url_in_browser",
    description="Open a URL in the default system web browser.",
    parameters={
        "url": {"type": "string", "description": "Full URL to open (must start with http:// or https://)"},
    },
    confirm=True,
)
async def open_url_in_browser(url: str) -> str:
    """Open url in default browser. Validates URL scheme before opening."""
    import webbrowser
    url = url.strip()
    if not url.startswith(("http://", "https://")):
        raise ValueError(f"Unsafe URL scheme rejected: {url!r}. Only http/https allowed.")
    webbrowser.open(url)
    return f"Opened in browser: {url}"


# ── 2. Play music / media ─────────────────────────────────────────────────────

@os_tool(
    name="play_music",
    description="Play music or media using the system's default media player or music app.",
    parameters={
        "query": {"type": "string", "description": "Song, artist, playlist name, or file path to play (optional — omit to resume/play default)"},
    },
    confirm=True,
)
async def play_music(query: str = "") -> str:
    """Play music or media using the system's default media player or music app.

    Handles:
    - Any media file path: .mp3 .mkv .mp4 .wav .flac .ogg .m4a .avi etc.
    - Music apps: Spotify, VLC, mpv, rhythmbox, playerctl
    - Resume/play current track when no query given

    Platform support:
    - macOS: afplay (files), Music app, or mpv/vlc
    - Linux: xdg-open (any file), playerctl, mpv, vlc, rhythmbox, cvlc
    - Windows: os.startfile (any file), wmplayer, Spotify
    """
    import shutil
    import subprocess

    platform = sys.platform
    query = query.strip()

    # Resolve file path — expand ~ and check existence
    file_path: Path | None = None
    if query:
        candidate = Path(query).expanduser()
        if candidate.exists():
            file_path = candidate

    if platform == "darwin":
        if file_path:
            # afplay for audio; for video/mkv use open (QuickTime/VLC)
            suffix = file_path.suffix.lower()
            if suffix in (".mp3", ".wav", ".flac", ".aac", ".m4a", ".ogg", ".aiff"):
                subprocess.Popen(["afplay", str(file_path)])
                return f"Playing: {file_path.name}"
            else:
                subprocess.Popen(["open", str(file_path)])
                return f"Opened with default app: {file_path.name}"
        if shutil.which("mpv"):
            subprocess.Popen(["mpv", "--no-video", query] if query else ["mpv"])
            return f"Playing via mpv: {query or 'default'}"
        subprocess.Popen(["open", "-a", "Music"])
        return "Music app opened" + (f" — searching: {query}" if query else "")

    elif platform.startswith("linux"):
        # play_target: always the fully-resolved path string (never raw ~ query)
        play_target = str(file_path) if file_path else query

        # 1. File path → mpv first (best quality), xdg-open as fallback
        if file_path:
            if shutil.which("mpv"):
                subprocess.Popen(["mpv", str(file_path)])
                return f"Playing via mpv: {file_path.name}"
            subprocess.Popen(["xdg-open", str(file_path)])
            return f"Opened with default media app: {file_path.name}"

        # 2. playerctl — controls currently running player (Spotify, VLC, etc.)
        if shutil.which("playerctl"):
            if query and not any(x in query.lower() for x in ("resume", "play", "music")):
                # Try Spotify URI search
                uri = f"spotify:search:{query.replace(' ', '%20')}"
                r = subprocess.run(
                    ["playerctl", "--player=spotify", "open", uri],
                    capture_output=True, timeout=5
                )
                if r.returncode == 0:
                    return f"Searching Spotify: {query}"
            subprocess.run(["playerctl", "play"], capture_output=True, timeout=5)
            return f"Resumed playback via playerctl"

        # 3. mpv — versatile, plays everything
        if shutil.which("mpv"):
            if play_target:
                subprocess.Popen(["mpv", play_target])
                return f"Playing via mpv: {play_target}"
            # No specific file — launch mpv with ~/Music or cwd if it has media
            for music_dir in (Path.cwd(), Path("~/Music").expanduser(), Path("~/Videos").expanduser()):
                if music_dir.exists():
                    media = [f for f in sorted(music_dir.iterdir())
                             if f.is_file() and f.suffix.lower() in {".mp3",".wav",".flac",".ogg",".m4a",".mp4",".mkv"}]
                    if media:
                        subprocess.Popen(["mpv"] + [str(f) for f in media])
                        return f"Playing {len(media)} file(s) via mpv from {music_dir.name}/"
            subprocess.Popen(["mpv", "--idle"])
            return "Opened mpv — drag a file in or provide a path"

        # 4. vlc / cvlc (headless VLC)
        for player in ("vlc", "cvlc"):
            if shutil.which(player):
                if play_target:
                    subprocess.Popen([player, play_target])
                    return f"Playing via {player}: {play_target}"
                subprocess.Popen([player])
                return f"Opened {player}"

        # 5. rhythmbox
        if shutil.which("rhythmbox-client"):
            subprocess.Popen(["rhythmbox-client", "--play"])
            return "Resumed via Rhythmbox"

        # 6. Last resort — xdg-open on target (URL or file)
        if play_target:
            subprocess.Popen(["xdg-open", play_target])
            return f"Opened: {play_target}"

        return (
            "No media player found. Install one: "
            "sudo apt install mpv   OR   sudo apt install vlc   OR   sudo apt install playerctl"
        )

    elif platform == "win32":
        if file_path:
            os.startfile(str(file_path))
            return f"Playing: {file_path.name}"
        subprocess.Popen(
            ["start", f"spotify:search:{query.replace(' ', '%20')}"], shell=True
        )
        return f"Launched Spotify search: {query or 'music'}"

    return f"play_music: unsupported platform {platform}"


# ── 3. Send email ─────────────────────────────────────────────────────────────

@os_tool(
    name="send_email",
    description="Send an email to a recipient. Uses system mail command or configured SMTP.",
    parameters={
        "to": {"type": "string", "description": "Recipient email address"},
        "subject": {"type": "string", "description": "Email subject line"},
        "body": {"type": "string", "description": "Email body text"},
    },
    confirm=True,  # always require explicit confirmation — sending email is irreversible
)
async def send_email(to: str, subject: str, body: str) -> str:
    """Send email. Tries: configured SMTP → system mail → mutt → error.

    Never sends without user confirmation (confirm=True enforces this in executor.py).
    Email address is validated with a basic regex before any attempt.
    """
    import shutil
    import subprocess

    # Validate recipient
    to = to.strip()
    if not re.match(r'^[^@\s]+@[^@\s]+\.[^@\s]+$', to):
        raise ValueError(f"Invalid email address: {to!r}")

    subject = subject.strip() or "(no subject)"
    body = body.strip()

    # Try: system `mail` command (sendmail-compatible)
    if shutil.which("mail"):
        proc = subprocess.run(
            ["mail", "-s", subject, to],
            input=body, text=True, capture_output=True, timeout=15
        )
        if proc.returncode == 0:
            return f"Email sent to {to} via system mail"
        return f"mail command failed: {proc.stderr[:200]}"

    # Try: mutt
    if shutil.which("mutt"):
        proc = subprocess.run(
            ["mutt", "-s", subject, to],
            input=body, text=True, capture_output=True, timeout=15
        )
        if proc.returncode == 0:
            return f"Email sent to {to} via mutt"

    # Try: configured SMTP via aicli config
    try:
        from ..config import get_api_key
        smtp_host = get_api_key("SMTP_HOST") or os.environ.get("SMTP_HOST")
        smtp_user = get_api_key("SMTP_USER") or os.environ.get("SMTP_USER")
        smtp_pass = get_api_key("SMTP_PASS") or os.environ.get("SMTP_PASS")
        smtp_port = int(get_api_key("SMTP_PORT") or os.environ.get("SMTP_PORT") or "587")

        if smtp_host and smtp_user and smtp_pass:
            import smtplib
            from email.message import EmailMessage
            msg = EmailMessage()
            msg["From"] = smtp_user
            msg["To"] = to
            msg["Subject"] = subject
            msg.set_content(body)

            with smtplib.SMTP(smtp_host, smtp_port, timeout=15) as server:
                server.starttls()
                server.login(smtp_user, smtp_pass)
                server.send_message(msg)
            return f"Email sent to {to} via SMTP ({smtp_host})"
    except Exception as e:
        pass

    return (
        f"Could not send email: no mail command or SMTP configured.\n"
        f"Configure SMTP: aicli config set SMTP_HOST mail.example.com\n"
        f"               aicli config set SMTP_USER you@example.com\n"
        f"               aicli config set SMTP_PASS yourpassword"
    )


# ── 4. Read file content ──────────────────────────────────────────────────────

@os_tool(
    name="read_file_content",
    description="Read and return the contents of a local file. Size-capped at 50 KB.",
    parameters={
        "file_path": {"type": "string", "description": "Absolute or relative path to the file to read"},
    },
    confirm=False,  # read-only — safe without confirmation
    safe=True,      # skip audit log for reads
)
async def read_file_content(file_path: str) -> str:
    """Read a file and return its content, capped at MAX_FILE_BYTES (50 KB).

    Security: files larger than 50 KB are truncated with a warning to prevent
    prompt injection attacks via large file uploads.
    """
    path = Path(file_path.strip()).expanduser().resolve()
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")
    if not path.is_file():
        raise ValueError(f"Not a file: {path}")

    raw = path.read_bytes()
    if len(raw) > MAX_FILE_BYTES:
        truncated = True
        raw = raw[:MAX_FILE_BYTES]
    else:
        truncated = False

    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        text = raw.decode("latin-1", errors="replace")

    suffix = f"\n\n[TRUNCATED — file is larger than {MAX_FILE_BYTES // 1024} KB]" if truncated else ""
    return text + suffix


# ── 5. Write / create file ────────────────────────────────────────────────────

@os_tool(
    name="write_file_content",
    description="Write content to a local file. Creates the file if it does not exist.",
    parameters={
        "file_path": {"type": "string", "description": "Path to write (absolute or relative)"},
        "content": {"type": "string", "description": "Text content to write to the file"},
        "append": {"type": "boolean", "description": "If true, append instead of overwrite (default: false)"},
    },
    confirm=True,  # destructive — always confirm
)
async def write_file_content(file_path: str, content: str, append: bool = False) -> str:
    """Write content to a file with home-dir guard and size limit."""
    path = Path(file_path.strip()).expanduser().resolve()
    home = Path.home().resolve()
    cwd = Path.cwd().resolve()

    # Security: only write inside home dir or cwd — block /etc, /usr, etc.
    if not (str(path).startswith(str(home)) or str(path).startswith(str(cwd))):
        raise PermissionError(
            f"Write blocked: {path} is outside home directory and cwd.\n"
            f"aicli tools only write inside {home} or {cwd}"
        )

    content_bytes = content.encode("utf-8")
    if len(content_bytes) > MAX_WRITE_BYTES:
        raise ValueError(f"Content too large: {len(content_bytes)//1024} KB > {MAX_WRITE_BYTES//1024} KB limit")

    path.parent.mkdir(parents=True, exist_ok=True)
    mode = "a" if append else "w"
    path.write_text(content, encoding="utf-8") if not append else open(path, "a").write(content)
    action = "Appended to" if append else "Wrote"
    return f"{action} {path} ({len(content_bytes)} bytes)"


# ── 6. Copy to clipboard ──────────────────────────────────────────────────────

@os_tool(
    name="copy_to_clipboard",
    description="Copy text to the system clipboard.",
    parameters={
        "text": {"type": "string", "description": "Text to copy to clipboard"},
    },
    confirm=False,  # read-from-LLM/write-to-clipboard — low risk, no confirmation needed
    safe=True,
)
async def copy_to_clipboard(text: str) -> str:
    """Copy text to clipboard using platform-appropriate tool."""
    import shutil
    import subprocess

    if sys.platform == "darwin":
        proc = subprocess.run(["pbcopy"], input=text, text=True, capture_output=True, timeout=5)
        return "Copied to clipboard (macOS pbcopy)"

    elif sys.platform.startswith("linux"):
        # Try xclip, then xsel, then wl-copy (Wayland)
        for cmd in [["xclip", "-selection", "clipboard"], ["xsel", "--clipboard", "--input"], ["wl-copy"]]:
            if shutil.which(cmd[0]):
                subprocess.run(cmd, input=text, text=True, capture_output=True, timeout=5)
                return f"Copied to clipboard ({cmd[0]})"
        return "No clipboard tool found. Install xclip, xsel, or wl-copy."

    elif sys.platform == "win32":
        subprocess.run(["clip"], input=text, text=True, capture_output=True, timeout=5)
        return "Copied to clipboard (Windows clip)"

    return "copy_to_clipboard: unsupported platform"


# ── 7. Run shell command (safe wrapper — still requires confirm) ───────────────

# Sandboxing constants (opt-in via AICLI_SANDBOX=1)
# MAX_OUTPUT_BYTES caps stdout+stderr to prevent prompt-flooding from noisy cmds.
import shutil as _shutil

MAX_OUTPUT_BYTES = 32_768       # 32 KB output cap
_SANDBOX_ENV_VAR = "AICLI_SANDBOX"


def _sandbox_available() -> bool:
    """Return True if firejail is on PATH and AICLI_SANDBOX=1 is set."""
    import os
    return os.environ.get(_SANDBOX_ENV_VAR, "0") == "1" and _shutil.which("firejail") is not None


def _build_sandboxed_cmd(command: str) -> list:
    """Wrap command in firejail with safe defaults.

    Flags:
      --quiet        suppress firejail banner
      --noprofile    no implicit system profile
      --noroot       drop effective root even if caller is root
      --private-tmp  fresh /tmp — can't read prior temp files
      --net=none     no network (override: AICLI_SANDBOX_NET=1)
    """
    import os
    args = ["firejail", "--quiet", "--noprofile", "--noroot", "--private-tmp"]
    if os.environ.get("AICLI_SANDBOX_NET", "0") != "1":
        args.append("--net=none")
    args += ["--", "bash", "-c", command]
    return args


@os_tool(
    name="run_shell_command",
    description="Execute a shell command and return its output. Use for system tasks that other tools don't cover.",
    parameters={
        "command": {"type": "string", "description": "Shell command to execute"},
        "timeout": {"type": "integer", "description": "Timeout in seconds (default: 30, max: 120)"},
        "working_dir": {"type": "string", "description": "Working directory to run the command in (default: current directory)"},
    },
    confirm=True,  # always confirm shell execution
)
async def run_shell_command(command: str, timeout: int = 30, working_dir: str = "") -> str:
    """Execute a shell command with timeout guard and optional working directory.

    Better than ShellGPT: always confirms, always logs, caps at 120s,
    supports explicit working directory so multi-step tasks stay in context.

    Sandboxing (opt-in):
        AICLI_SANDBOX=1   — wrap in firejail when available (no net, private /tmp)
        AICLI_SANDBOX_NET=1 — allow network access inside sandbox
        Falls back silently to unsandboxed if firejail is not installed.

    Output cap: stdout+stderr truncated at 32 KB to prevent prompt flooding.
    """
    import subprocess

    timeout = min(max(timeout, 1), 120)  # clamp 1–120s

    # Resolve working directory if provided
    cwd = None
    if working_dir:
        cwd_path = Path(working_dir.strip()).expanduser().resolve()
        if not cwd_path.exists():
            raise FileNotFoundError(f"Working directory not found: {cwd_path}")
        if not cwd_path.is_dir():
            raise NotADirectoryError(f"Not a directory: {cwd_path}")
        cwd = str(cwd_path)

    # Build command — firejail-sandboxed or direct
    sandboxed = _sandbox_available()
    if sandboxed:
        cmd_args = _build_sandboxed_cmd(command)
        run_kwargs: dict = dict(capture_output=True, text=True, timeout=timeout, cwd=cwd)
    else:
        cmd_args = command
        run_kwargs = dict(shell=True, capture_output=True, text=True, timeout=timeout, cwd=cwd)

    try:
        result = subprocess.run(cmd_args, **run_kwargs)
        out = result.stdout
        err = result.stderr

        # Cap output to prevent prompt-flooding from verbose commands
        if len(out) > MAX_OUTPUT_BYTES:
            out = out[:MAX_OUTPUT_BYTES] + f"\n... [output truncated at {MAX_OUTPUT_BYTES} bytes]"
        if len(err) > MAX_OUTPUT_BYTES:
            err = err[:MAX_OUTPUT_BYTES] + f"\n... [stderr truncated at {MAX_OUTPUT_BYTES} bytes]"

        out = out.strip()
        err = err.strip()

        if result.returncode != 0:
            raise RuntimeError(f"Command failed (exit {result.returncode}):\n{err or out}")
        return out or "(no output)"
    except subprocess.TimeoutExpired:
        raise TimeoutError(f"Command timed out after {timeout}s: {command!r}")


# ── 13. Browse and pick a media file ─────────────────────────────────────────

MEDIA_EXTENSIONS = {
    ".mp3", ".mp4", ".mkv", ".wav", ".flac", ".ogg", ".m4a",
    ".aac", ".avi", ".mov", ".webm", ".opus", ".aiff", ".wma",
}

@os_tool(
    name="browse_media",
    description="List media files in a directory and let the user pick one by number to play.",
    parameters={
        "directory": {"type": "string", "description": "Directory to scan (default: ~/Music then ~/Videos then ~)"},
        "filter": {"type": "string", "description": "Optional filter: 'audio', 'video', or leave empty for all media"},
    },
    confirm=False,
    safe=True,
)
async def browse_media(directory: str = "", filter: str = "") -> str:
    """Scan a directory for media files and present a numbered pick-list.

    - "browse my music" → scans ~/Music
    - "browse media in this dir" / "this directory" / "." / "here" → uses cwd
    - "play the song in this directory" → auto-plays if only one file found
    - Type a number and press Enter → plays that file immediately
    - 0 or Enter → cancel

    Supports: mp3 mp4 mkv wav flac ogg m4a aac avi mov webm opus aiff wma
    """
    import subprocess

    # Resolve directory
    # "this dir", "here", ".", "current" → use cwd
    # Resolve directory
    # Accepts: absolute path, ~/relative, ".", cwd keywords, or empty (auto-detect)
    cwd_keywords = {".", "here", "this dir", "this directory", "current", "current directory", "cwd"}
    dir_stripped = directory.strip()
    search_dirs: list[Path] = []

    if dir_stripped and dir_stripped.lower() not in cwd_keywords:
        # Explicit path given — use it directly
        d = Path(dir_stripped).expanduser().resolve()
        if d.exists():
            search_dirs = [d]
        else:
            return f"Directory not found: {dir_stripped}"
    elif dir_stripped.lower() in cwd_keywords:
        # Explicit cwd request
        search_dirs = [Path.cwd().resolve()]
    else:
        # Nothing given — scan cwd first, then ~/Music, ~/Videos
        cwd_resolved = Path.cwd().resolve()
        cwd_files = [
            f for f in cwd_resolved.iterdir()
            if f.is_file() and f.suffix.lower() in MEDIA_EXTENSIONS
        ]
        if cwd_files:
            search_dirs = [cwd_resolved]
        else:
            for candidate in ("~/Music", "~/Videos", "~/Downloads", "~"):
                p = Path(candidate).expanduser()
                if p.exists():
                    search_dirs.append(p)

    # Collect media files
    filter_lower = filter.lower()
    audio_exts = {".mp3", ".wav", ".flac", ".ogg", ".m4a", ".aac", ".opus", ".aiff", ".wma"}
    video_exts = {".mp4", ".mkv", ".avi", ".mov", ".webm"}

    if filter_lower == "audio":
        allowed = audio_exts
    elif filter_lower == "video":
        allowed = video_exts
    else:
        allowed = MEDIA_EXTENSIONS

    files: list[Path] = []
    for d in search_dirs:
        for f in sorted(d.iterdir()):
            if f.is_file() and f.suffix.lower() in allowed:
                files.append(f)
        if files:
            break  # stop at first dir that has media

    if not files:
        dirs_str = ", ".join(str(d) for d in search_dirs[:3])
        return (
            f"No media files found in: {dirs_str}\n"
            f"Supported formats: {', '.join(sorted(allowed))}"
        )

    # Auto-play if only one file — no menu needed
    if len(files) == 1:
        print(f"  Found 1 file: {files[0].name}")
        return await play_music(str(files[0]))

    # Print numbered list
    scan_dir = search_dirs[0] if search_dirs else Path.cwd()
    print(f"\n  {len(files)} media files in {scan_dir}\n")
    for i, f in enumerate(files, 1):
        size_mb = f.stat().st_size / (1024 * 1024)
        ext = f.suffix.lower().lstrip(".")
        print(f"  [{i:>2}] {f.name:<40} {size_mb:>6.1f} MB  {ext}")

    # Get user input
    try:
        choice_str = input("\n  Pick a number (0 or Enter to cancel): ").strip()
        if not choice_str or choice_str == "0":
            return "Cancelled."
        choice = int(choice_str)
        if not 1 <= choice <= len(files):
            return f"Invalid choice: {choice}  (1–{len(files)})"
    except (ValueError, EOFError):
        return "Invalid input."

    selected = files[choice - 1]
    return await play_music(str(selected))

# ── Path auto-detection helper (used by default.py) ───────────────────────────

# Regex to detect file/directory paths embedded in a prompt.
# Matches: /absolute/path, ~/home/path, ./relative, ../up
# Does NOT match: URLs (http://...), flag strings (--file)
_PATH_RE = re.compile(
    r'(?<!\w)'                   # not preceded by a word char
    r'(?:'
        r'(?:/[^\s,;"\'\)]+)'   # /absolute/path
        r'|(?:~/[^\s,;"\'\)]+)' # ~/home/path
        r'|(?:\./[^\s,;"\'\)]+)'# ./relative
        r'|(?:\.\./[^\s,;"\'\)]+)'  # ../up
    r')'
    r'(?!\w)',                   # not followed by a word char
    re.UNICODE,
)


def extract_file_paths_from_prompt(prompt: str) -> list[str]:
    """Find all file/directory paths embedded in a natural-language prompt.

    Returns only paths that actually exist on the filesystem, so false
    positives (version numbers like 1.5.0, flags like --config) are filtered.

    Security: always returns resolved absolute paths for downstream safety checks.

    Example:
        "summarize /tmp/docs/report.txt and compare to ./notes.md"
        → ["/tmp/docs/report.txt", "/path/to/cwd/notes.md"]
    """
    found = []
    for match in _PATH_RE.finditer(prompt):
        raw = match.group(0)
        try:
            p = Path(raw).expanduser().resolve()
            if p.exists() and p.is_file():
                found.append(str(p))
        except Exception:
            pass
    return found


# ── 8. Send desktop notification ─────────────────────────────────────────────

@os_tool(
    name="send_notification",
    description="Send a desktop notification (system tray / notification center).",
    parameters={
        "title": {"type": "string", "description": "Notification title"},
        "body":  {"type": "string", "description": "Notification body text"},
    },
    confirm=False,  # notifications are non-destructive, no confirmation needed
    safe=True,
)
async def send_notification(title: str, body: str) -> str:
    """Send a desktop notification cross-platform.

    - macOS: osascript display notification
    - Linux: notify-send (libnotify)
    - Windows: win10toast or powershell balloon
    """
    import shutil
    import subprocess

    title = title.strip()
    body = body.strip()

    if sys.platform == "darwin":
        script = f'display notification "{body}" with title "{title}"'
        subprocess.run(["osascript", "-e", script], capture_output=True, timeout=5)
        return f"Notification sent (macOS): {title}"

    elif sys.platform.startswith("linux"):
        if shutil.which("notify-send"):
            subprocess.run(["notify-send", title, body], capture_output=True, timeout=5)
            return f"Notification sent (notify-send): {title}"
        return "notify-send not found. Install libnotify: sudo apt install libnotify-bin"

    elif sys.platform == "win32":
        # Try win10toast if installed, fallback to PowerShell balloon
        try:
            from win10toast import ToastNotifier
            ToastNotifier().show_toast(title, body, duration=5)
            return f"Notification sent (win10toast): {title}"
        except ImportError:
            pass
        ps_script = (
            f'[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, '
            f'ContentType = WindowsRuntime] > $null; '
            f'$t = [Windows.UI.Notifications.ToastTemplateType]::ToastText02; '
            f'$xml = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent($t); '
            f'$xml.GetElementsByTagName("text")[0].AppendChild($xml.CreateTextNode("{title}")) > $null; '
            f'$xml.GetElementsByTagName("text")[1].AppendChild($xml.CreateTextNode("{body}")) > $null; '
            f'[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("aicli")'
            f'.Show([Windows.UI.Notifications.ToastNotification]::new($xml))'
        )
        subprocess.run(["powershell", "-Command", ps_script], capture_output=True, timeout=10)
        return f"Notification sent (PowerShell): {title}"

    return f"send_notification: unsupported platform {sys.platform}"


# ── 9. Get clipboard content ──────────────────────────────────────────────────

@os_tool(
    name="get_clipboard",
    description="Read and return the current clipboard contents.",
    parameters={},
    confirm=False,  # read-only
    safe=True,
)
async def get_clipboard() -> str:
    """Read clipboard content cross-platform.

    - macOS: pbpaste
    - Linux: xclip / xsel / wl-paste
    - Windows: PowerShell Get-Clipboard
    """
    import shutil
    import subprocess

    if sys.platform == "darwin":
        result = subprocess.run(["pbpaste"], capture_output=True, text=True, timeout=5)
        return result.stdout or "(clipboard empty)"

    elif sys.platform.startswith("linux"):
        for cmd in [["xclip", "-selection", "clipboard", "-o"],
                    ["xsel", "--clipboard", "--output"],
                    ["wl-paste"]]:
            if shutil.which(cmd[0]):
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
                return result.stdout or "(clipboard empty)"
        return "No clipboard tool found. Install xclip, xsel, or wl-paste."

    elif sys.platform == "win32":
        result = subprocess.run(
            ["powershell", "-Command", "Get-Clipboard"],
            capture_output=True, text=True, timeout=5
        )
        return result.stdout.strip() or "(clipboard empty)"

    return f"get_clipboard: unsupported platform {sys.platform}"


# ── 10. Open file with default application ────────────────────────────────────

@os_tool(
    name="open_file",
    description="Open a file or directory with the system's default application (like double-clicking).",
    parameters={
        "path": {"type": "string", "description": "Absolute or relative path to file or directory to open"},
    },
    confirm=True,
)
async def open_file(path: str) -> str:
    """Open any file/directory with the default OS application.

    Better than open_url_in_browser: handles PDFs, images, folders, code files, etc.
    Uses: xdg-open (Linux), open (macOS), start (Windows).
    """
    import shutil
    import subprocess

    p = Path(path.strip()).expanduser().resolve()
    if not p.exists():
        raise FileNotFoundError(f"Path not found: {p}")

    if sys.platform == "darwin":
        subprocess.Popen(["open", str(p)])
        return f"Opened with default app (macOS): {p}"

    elif sys.platform.startswith("linux"):
        if shutil.which("xdg-open"):
            subprocess.Popen(["xdg-open", str(p)])
            return f"Opened with xdg-open: {p}"
        return f"xdg-open not found. Install xdg-utils."

    elif sys.platform == "win32":
        os.startfile(str(p))
        return f"Opened with default app (Windows): {p}"

    return f"open_file: unsupported platform {sys.platform}"


# ── 11. Search web (callable as a tool) ──────────────────────────────────────

@os_tool(
    name="search_web",
    description="Search the web and return a summary of results. Uses aicli's 6-backend search chain.",
    parameters={
        "query": {"type": "string", "description": "Search query string"},
    },
    confirm=False,  # read-only, no side effects
    safe=True,
)
async def search_web(query: str) -> str:
    """Search the web using aicli's existing 6-backend chain and return results."""
    try:
        from ..web import web_search
        result = await web_search(query.strip())
        return result or f"No results found for: {query}"
    except ImportError:
        # Fallback: use subprocess to run aicli ask --web --quiet
        import subprocess
        result = subprocess.run(
            ["aicli", "ask", "--web", "--quiet", query],
            capture_output=True, text=True, timeout=30
        )
        return result.stdout.strip() or f"No results for: {query}"
    except Exception as e:
        return f"Web search error: {e}"


# ── 12. Get system info ───────────────────────────────────────────────────────

@os_tool(
    name="get_system_info",
    description="Return OS, hostname, CPU, memory, and disk usage. Useful for diagnostics.",
    parameters={
        "detail": {"type": "string", "description": "What to check: 'all', 'memory', 'disk', 'cpu', 'os' (default: all)"},
    },
    confirm=False,  # read-only
    safe=True,
)
async def get_system_info(detail: str = "all") -> str:
    """Return system information. Cross-platform using stdlib only."""
    import platform as _platform
    import shutil
    import subprocess

    detail = detail.strip().lower() or "all"
    lines = []

    if detail in ("all", "os"):
        lines.append(f"OS: {_platform.system()} {_platform.release()} ({_platform.machine()})")
        lines.append(f"Hostname: {_platform.node()}")
        lines.append(f"Python: {_platform.python_version()}")

    if detail in ("all", "cpu"):
        try:
            import psutil
            cpu_pct = psutil.cpu_percent(interval=0.5)
            cpu_count = psutil.cpu_count()
            lines.append(f"CPU: {cpu_count} cores, {cpu_pct}% used")
        except ImportError:
            # fallback: uptime / /proc/cpuinfo
            if sys.platform.startswith("linux"):
                r = subprocess.run(["nproc"], capture_output=True, text=True)
                lines.append(f"CPU cores: {r.stdout.strip()}")

    if detail in ("all", "memory"):
        try:
            import psutil
            mem = psutil.virtual_memory()
            lines.append(f"Memory: {mem.used // (1024**2)} MB used / {mem.total // (1024**2)} MB total ({mem.percent}%)")
        except ImportError:
            if sys.platform.startswith("linux"):
                r = subprocess.run(["free", "-h"], capture_output=True, text=True)
                lines.append(f"Memory:\n{r.stdout.strip()}")

    if detail in ("all", "disk"):
        try:
            import psutil
            disk = psutil.disk_usage("/")
            lines.append(f"Disk (/): {disk.used // (1024**3)} GB used / {disk.total // (1024**3)} GB total ({disk.percent}%)")
        except ImportError:
            r = subprocess.run(["df", "-h", "/"], capture_output=True, text=True)
            lines.append(f"Disk:\n{r.stdout.strip()}")

    return "\n".join(lines) if lines else f"Unknown detail: {detail}"
