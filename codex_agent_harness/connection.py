"""Persist an explicitly configured outbound Master connection for a Slave."""

from __future__ import annotations

import json
import os
from pathlib import Path


CONFIG_PATH = Path.home() / ".codex-agent-harness" / "agent-connection.json"


def load() -> dict[str, str]:
    try:
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    return {key: str(data.get(key) or "") for key in ("ssh_target", "ssh_identity", "token")}


def save(values: dict[str, str]) -> dict[str, str]:
    current = load()
    for key in current:
        if key in values:
            current[key] = str(values[key]).strip()
    target = current["ssh_target"]
    token = current["token"]
    if bool(target) != bool(token):
        raise ValueError("SSH target and report token must both be set, or both be empty")
    if target and (target.startswith("-") or any(char.isspace() for char in target)):
        raise ValueError("SSH target must be a host alias or user@host without whitespace")
    if current["ssh_identity"]:
        identity = Path(current["ssh_identity"]).expanduser()
        if not identity.is_file():
            raise ValueError("SSH identity file was not found")
        current["ssh_identity"] = str(identity.resolve())
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary = CONFIG_PATH.with_name(CONFIG_PATH.name + ".tmp")
    temporary.write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, CONFIG_PATH)
    if os.name != "nt":
        CONFIG_PATH.chmod(0o600)
    return current
