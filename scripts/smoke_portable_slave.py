"""Check that a packaged Slave can open its local window without Python."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: smoke_portable_slave.py SLAVE_BINARY")
    executable = str(Path(sys.argv[1]).resolve())
    with tempfile.TemporaryDirectory(prefix="cah-slave-smoke-") as profile:
        environment = os.environ.copy()
        environment["HOME"] = profile
        environment["USERPROFILE"] = profile
        expected_codex = None
        if os.name == "nt":
            expected_codex = (Path(profile) / ".codex" / "packages" / "standalone" /
                              "releases" / "0.999.0" / "bin" / "codex.exe")
            expected_codex.parent.mkdir(parents=True)
            expected_codex.write_bytes(b"search target")
        for name in ("CODEX_AGENT_HARNESS_REPORT_TOKEN", "CODEX_AGENT_HARNESS_SSH_TARGET"):
            environment.pop(name, None)
        process = subprocess.Popen(
            [executable, "--launcher-only"], env=environment,
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        try:
            time.sleep(3)
            if process.poll() is not None:
                error = process.stderr.read().decode("utf-8", errors="replace")
                raise RuntimeError(f"Slave window exited immediately: {error}")
            if expected_codex:
                import json
                settings = json.loads((Path(profile) / ".codex-agent-harness" /
                                       "local-tools.json").read_text(encoding="utf-8"))
                if settings.get("codex") != str(expected_codex):
                    raise RuntimeError(f"Slave chose {settings.get('codex')!r}; expected {str(expected_codex)!r}")
            print("PACKAGED_SLAVE_WINDOW_STARTED")
        finally:
            process.terminate()
            process.wait(timeout=10)


if __name__ == "__main__":
    main()
