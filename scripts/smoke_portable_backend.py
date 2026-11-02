"""Start a packaged Master in an isolated profile and check its API."""

from __future__ import annotations

import base64
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit("usage: smoke_portable_backend.py MASTER_BINARY PORT")
    executable = str(Path(sys.argv[1]).resolve())
    port = int(sys.argv[2])
    with tempfile.TemporaryDirectory(prefix="cah-package-smoke-") as profile:
        environment = os.environ.copy()
        environment["HOME"] = profile
        environment["USERPROFILE"] = profile
        expected_codex = None
        if os.name == "nt":
            expected_codex = (Path(profile) / ".codex" / "packages" / "standalone" /
                              "releases" / "0.999.0" / "bin" / "codex.exe")
            expected_codex.parent.mkdir(parents=True)
            expected_codex.write_bytes(b"search target")
        for name in ("REPORT_TOKEN", "DASHBOARD_USER", "DASHBOARD_PASSWORD"):
            environment.pop(name, None)
        process = subprocess.Popen(
            [executable, "--no-local-slave", "--port", str(port)], env=environment,
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        try:
            base_url = f"http://127.0.0.1:{port}"
            for _ in range(50):
                if process.poll() is not None:
                    error = process.stderr.read().decode("utf-8", errors="replace")
                    raise RuntimeError(f"Master exited before health check: {error}")
                try:
                    with urlopen(base_url + "/healthz", timeout=0.5) as response:
                        if json.load(response).get("ok"):
                            break
                except (OSError, URLError):
                    time.sleep(0.2)
            else:
                raise RuntimeError("Master health check timed out")
            settings = json.loads((Path(profile) / ".codex-agent-harness" /
                                   "master-credentials.json").read_text(encoding="utf-8"))
            configured = json.loads((Path(profile) / ".codex-agent-harness" /
                                     "local-tools.json").read_text(encoding="utf-8"))
            if not configured.get("terminal"):
                raise RuntimeError("Master did not discover a terminal")
            if expected_codex and configured.get("codex") != str(expected_codex):
                raise RuntimeError(f"Master chose {configured.get('codex')!r}; expected {str(expected_codex)!r}")
            basic = base64.b64encode(
                f"{settings['DASHBOARD_USER']}:{settings['DASHBOARD_PASSWORD']}".encode()
            ).decode("ascii")
            request = Request(base_url + "/api/local-tools",
                              headers={"Authorization": "Basic " + basic})
            with urlopen(request, timeout=3) as response:
                data = json.load(response)
            if not {"configured", "missing", "suggestions"} <= set(data):
                raise RuntimeError("Local program settings API missing in package")
            with urlopen(Request(base_url + "/", headers={"Authorization": "Basic " + basic}),
                         timeout=3) as response:
                if b"CodexAgentHarness" not in response.read():
                    raise RuntimeError("Dashboard HTML missing in package")
            stopped = subprocess.run([executable, "--stop", "--port", str(port)],
                                     env=environment, stdout=subprocess.DEVNULL,
                                     stderr=subprocess.PIPE, timeout=25,
                                     creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
            if stopped.returncode:
                raise RuntimeError(stopped.stderr.decode("utf-8", errors="replace"))
            process.wait(timeout=10)
            print("PACKAGED_MASTER_HEALTH_AND_STOP_OK")
        finally:
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=10)


if __name__ == "__main__":
    main()
