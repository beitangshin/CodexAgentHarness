"""Find local programs, keeping a user's valid choices when available."""

from __future__ import annotations

import json
import os
import shutil
import uuid
from pathlib import Path
from typing import Iterable


CONFIG_PATH = Path.home() / ".codex-agent-harness" / "local-tools.json"
KINDS = ("codex", "terminal", "ssh")
WINDOWS_CONSOLE = "windows-console"


def load() -> dict[str, str]:
    try:
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    return {kind: str(data.get(kind) or "") for kind in KINDS}


def save(values: dict[str, str]) -> dict[str, str]:
    current = load()
    for kind, raw in values.items():
        if kind not in KINDS:
            raise ValueError(f"Unknown local program: {kind}")
        value = str(raw).strip().strip('"')
        if value and not (kind == "terminal" and os.name == "nt" and value == WINDOWS_CONSOLE):
            path = Path(value).expanduser()
            if not path.is_absolute() or not path.is_file():
                raise ValueError(f"{kind}: choose an existing executable file with an absolute path")
            # Preserve alternatives such as /usr/bin/x-terminal-emulator: the
            # alias name determines which launch arguments we pass to it.
            value = str(path.absolute())
        current[kind] = value
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary = CONFIG_PATH.with_name(f"{CONFIG_PATH.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
    temporary.write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, CONFIG_PATH)
    if os.name != "nt":
        CONFIG_PATH.chmod(0o600)
    return current


def require(kind: str) -> str:
    if kind not in KINDS:
        raise ValueError(f"Unknown local program: {kind}")
    value = auto_configure((kind,))[kind]
    if not value:
        raise RuntimeError(f"Configure the local {kind} executable in Settings before using this action")
    if kind == "terminal" and os.name == "nt" and value == WINDOWS_CONSOLE:
        return value
    path = Path(value)
    if not path.is_file():
        raise RuntimeError(f"Configured {kind} executable was not found: {value}")
    if os.name != "nt" and not os.access(path, os.X_OK):
        raise RuntimeError(f"Configured {kind} file is not executable: {value}")
    return value


def _usable(kind: str, value: str) -> bool:
    if kind == "terminal" and os.name == "nt" and value == WINDOWS_CONSOLE:
        return True
    path = Path(value)
    return path.is_file() and (os.name == "nt" or os.access(path, os.X_OK))


def suggestions(kind: str) -> list[str]:
    if kind not in KINDS:
        raise ValueError(f"Unknown local program: {kind}")
    found: list[str] = []
    commands = {
        "codex": ["codex"],
        "terminal": ["powershell", "pwsh", "wt"] if os.name == "nt" else
                    ["x-terminal-emulator", "gnome-terminal", "konsole", "xfce4-terminal", "xterm"],
        "ssh": ["ssh"],
    }
    deferred: list[str] = []
    for command in commands[kind]:
        detected = shutil.which(command)
        if detected:
            value = str(Path(detected).absolute())
            # VS Code may place its extension's preview CLI on PATH. Prefer a
            # separately installed Codex CLI when one is available.
            if kind == "codex" and "openai.chatgpt-" in value.lower() and ".vscode" in value.lower():
                deferred.append(value)
            elif value not in found:
                found.append(value)
    home = Path.home()
    if os.name == "nt":
        system = Path(os.environ.get("SystemRoot", r"C:\Windows"))
        program_files = Path(os.environ.get("ProgramFiles", r"C:\Program Files"))
        local_app = Path(os.environ.get("LOCALAPPDATA", str(home / "AppData" / "Local")))
        app_data = Path(os.environ.get("APPDATA", str(home / "AppData" / "Roaming")))
        paths = {
            "codex": [app_data / "npm" / "codex.cmd", home / ".codex" / "bin" / "codex.exe",
                      *(path / "bin" / "codex.exe" for path in sorted(
                          (home / ".codex" / "packages" / "standalone" / "releases").glob("*"), reverse=True)),
                      *sorted((home / ".vscode" / "extensions").glob(
                          "openai.chatgpt-*/bin/windows-*/codex.exe"), reverse=True)],
            "terminal": [system / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe",
                         program_files / "PowerShell" / "7" / "pwsh.exe",
                         local_app / "Microsoft" / "WindowsApps" / "wt.exe"],
            "ssh": [system / "System32" / "OpenSSH" / "ssh.exe"],
        }
    else:
        paths = {
            "codex": [home / ".npm-global" / "bin" / "codex", home / ".local" / "bin" / "codex",
                      Path("/usr/local/bin/codex"), Path("/usr/bin/codex"),
                      *sorted((home / ".nvm" / "versions" / "node").glob("*/bin/codex"), reverse=True),
                      *sorted((home / ".vscode" / "extensions").glob(
                          "openai.chatgpt-*/bin/linux-*/codex"), reverse=True)],
            "terminal": [Path("/usr/bin/x-terminal-emulator"), Path("/usr/bin/gnome-terminal"),
                         Path("/usr/bin/konsole"), Path("/usr/bin/xfce4-terminal"), Path("/usr/bin/xterm")],
            "ssh": [Path("/usr/bin/ssh"), Path("/bin/ssh")],
        }
    for path in paths[kind]:
        value = str(path)
        if value not in found:
            found.append(value)
    for value in deferred:
        if value not in found:
            found.append(value)
    if kind == "terminal" and os.name == "nt":
        found.append(WINDOWS_CONSOLE)
    return found


def detect(kind: str) -> str:
    """Return the first installed candidate, without changing a saved choice."""
    for candidate in suggestions(kind):
        if _usable(kind, candidate):
            return candidate
    return ""


def auto_configure(kinds: Iterable[str] = KINDS) -> dict[str, str]:
    """Fill only missing or broken paths; leave valid user choices intact."""
    current = load()
    changes: dict[str, str] = {}
    for kind in kinds:
        if kind not in KINDS:
            raise ValueError(f"Unknown local program: {kind}")
        if not current[kind] or not _usable(kind, current[kind]):
            candidate = detect(kind)
            if candidate:
                changes[kind] = candidate
    return save(changes) if changes else current


def missing(kinds: Iterable[str] = KINDS) -> list[str]:
    requested = tuple(kinds)
    current = auto_configure(requested)
    return [kind for kind in requested if not current[kind] or not _usable(kind, current[kind])]
