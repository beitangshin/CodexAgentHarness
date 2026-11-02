"""Run the laptop dashboard and receiver on loopback only."""

from __future__ import annotations

import argparse
import json
import os
import secrets
import threading
import time
from pathlib import Path

import psutil
import uvicorn

from .agent import _report_loop
from . import local_tools


APP_DIR = Path.home() / ".codex-agent-harness"
CREDENTIALS_PATH = APP_DIR / "master-credentials.json"
PROCESS_PATH = APP_DIR / "master-process.json"


def _load_or_create_credentials() -> None:
    names = ("REPORT_TOKEN", "DASHBOARD_USER", "DASHBOARD_PASSWORD")
    if all(os.getenv(name) for name in names):
        return
    if CREDENTIALS_PATH.exists():
        values = json.loads(CREDENTIALS_PATH.read_text(encoding="utf-8"))
    else:
        values = {"REPORT_TOKEN": secrets.token_urlsafe(32), "DASHBOARD_USER": "admin",
                  "DASHBOARD_PASSWORD": secrets.token_urlsafe(24)}
        APP_DIR.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(CREDENTIALS_PATH, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            json.dump(values, output, ensure_ascii=False, indent=2)
    for name in names:
        if not values.get(name):
            raise ValueError(f"Master credentials file is missing {name}")
        os.environ[name] = str(values[name])


def _stop_master(port: int) -> None:
    if not PROCESS_PATH.exists():
        print("Master is already stopped")
        return
    info = json.loads(PROCESS_PATH.read_text(encoding="utf-8"))
    if info.get("port") != port:
        raise RuntimeError("Master process record belongs to a different port")
    try:
        process = psutil.Process(int(info["pid"]))
        if abs(process.create_time() - float(info["created"])) >= 1:
            raise RuntimeError("Master PID was reused; refusing to stop it")
        process.terminate()
        # On Unix a Master launched by another app can remain a zombie until
        # that app reaps it. A zombie has stopped, though psutil.wait() from
        # this unrelated process waits for its PID to disappear.
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            try:
                if not process.is_running() or process.status() == psutil.STATUS_ZOMBIE:
                    break
            except psutil.NoSuchProcess:
                break
            time.sleep(0.1)
        else:
            raise RuntimeError("Master did not stop within 8 seconds")
    except psutil.NoSuchProcess:
        pass
    PROCESS_PATH.unlink(missing_ok=True)


def _record_process(port: int) -> None:
    APP_DIR.mkdir(parents=True, exist_ok=True)
    process = psutil.Process()
    value = {"pid": process.pid, "created": process.create_time(), "port": port}
    temporary = PROCESS_PATH.with_name(PROCESS_PATH.name + ".tmp")
    temporary.write_text(json.dumps(value), encoding="utf-8")
    os.replace(temporary, PROCESS_PATH)


def _local_slave_args(port: int, token: str) -> argparse.Namespace:
    return argparse.Namespace(ssh_target=None, ssh_identity=None, ssh_port=22,
                              master_port=port, local_master=True, machine_id=None,
                              token=token, once=False)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the local CodexAgentHarness master")
    parser.add_argument("--port", type=int, default=8000, help="loopback port (default: 8000)")
    parser.add_argument("--no-local-slave", action="store_true",
                        help="disable the built-in reporter when a separate local Slave is running")
    parser.add_argument("--stop", action="store_true", help="stop a Master started by this application")
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("port must be between 1 and 65535")
    if args.stop:
        _stop_master(args.port)
        return
    local_tools.auto_configure(("codex", "terminal"))
    try:
        _load_or_create_credentials()
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    stop = threading.Event()
    reporter = None
    if not args.no_local_slave:
        reporter = threading.Thread(target=_report_loop,
                                    args=(_local_slave_args(args.port, os.environ["REPORT_TOKEN"]), stop),
                                    name="CodexAgentHarness local Slave", daemon=True)
        reporter.start()
    try:
        _record_process(args.port)
        uvicorn.run("codex_agent_harness.server:app", host="127.0.0.1", port=args.port, workers=1)
    finally:
        stop.set()
        if reporter:
            reporter.join(timeout=6)
        try:
            info = json.loads(PROCESS_PATH.read_text(encoding="utf-8"))
            if info.get("pid") == os.getpid():
                PROCESS_PATH.unlink(missing_ok=True)
        except (OSError, ValueError):
            pass


if __name__ == "__main__":
    main()
