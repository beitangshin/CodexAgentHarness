"""Register the Slave GUI to start at the current user's next login."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


APP_NAME = "CodexAgentHarness"
AUTOSTART_FILE = Path.home() / ".config" / "autostart" / "codex-agent-harness.desktop"
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def _command() -> list[str]:
    if getattr(sys, "frozen", False):
        if sys.platform.startswith("linux"):
            stable = Path.home() / ".local" / "bin" / "codex-agent-harness"
            try:
                if stable.is_file() and stable.resolve() == Path(sys.executable).resolve():
                    return [str(stable)]
            except OSError:
                pass
        return [sys.executable]
    return [sys.executable, "-m", "codex_agent_harness.agent"]


def _desktop_quote(value: str) -> str:
    escaped = value.replace("%", "%%").replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _desktop_contents() -> str:
    command = " ".join(_desktop_quote(value) for value in _command())
    return ("[Desktop Entry]\n"
            "Type=Application\n"
            "Name=CodexAgentHarness\n"
            "Comment=Start CodexAgentHarness Slave after login\n"
            f"Exec={command}\n"
            "Terminal=false\n"
            "X-GNOME-Autostart-enabled=true\n")


def is_registered() -> bool:
    if os.name == "nt":
        import winreg

        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_READ) as key:
                value, _ = winreg.QueryValueEx(key, APP_NAME)
            return value == subprocess.list2cmdline(_command())
        except OSError:
            return False
    if sys.platform.startswith("linux"):
        try:
            return AUTOSTART_FILE.read_text(encoding="utf-8") == _desktop_contents()
        except OSError:
            return False
    return False


def register() -> None:
    if os.name == "nt":
        import subprocess
        import winreg

        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, subprocess.list2cmdline(_command()))
        return
    if sys.platform.startswith("linux"):
        AUTOSTART_FILE.parent.mkdir(parents=True, exist_ok=True)
        temporary = AUTOSTART_FILE.with_name(f"{AUTOSTART_FILE.name}.{os.getpid()}.tmp")
        try:
            temporary.write_text(_desktop_contents(), encoding="utf-8")
            temporary.chmod(0o600)
            os.replace(temporary, AUTOSTART_FILE)
        finally:
            temporary.unlink(missing_ok=True)
        return
    raise OSError(f"Automatic startup is not supported on {sys.platform}")


def unregister() -> None:
    if os.name == "nt":
        import winreg

        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
                winreg.DeleteValue(key, APP_NAME)
        except FileNotFoundError:
            pass
        return
    if sys.platform.startswith("linux"):
        AUTOSTART_FILE.unlink(missing_ok=True)
        return
    raise OSError(f"Automatic startup is not supported on {sys.platform}")
