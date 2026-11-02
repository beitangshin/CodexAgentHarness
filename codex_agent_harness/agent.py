"""One reporter per machine; each report is a complete machine snapshot."""

from __future__ import annotations

import argparse
import json
import os
import platform
import re
import socket
import sys
import threading
import time
import uuid
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from .managed import (browse_directories, collect_managed, delete_instance, launch_terminal,
                      list_models, restart_instance, stop_instance)
from .interaction import answer_approval, augment_snapshot, ensure_bridges, send_task
from .ssh_tunnel import SshTunnel
from . import connection


def _machine_id(path: Path) -> str:
    if path.exists():
        return path.read_text(encoding="utf-8").strip()
    path.parent.mkdir(parents=True, exist_ok=True)
    value = str(uuid.uuid4())
    path.write_text(value, encoding="utf-8")
    return value


def _identity_path(hostname: str) -> Path:
    safe_name = re.sub(r"[^a-zA-Z0-9._-]", "_", hostname).lower()
    return Path.home() / ".codex-agent-harness" / f"machine-id-{safe_name}"


def _execute_command(command: dict) -> str | dict:
    action = command["action"]
    instance_id = command["instance_id"]
    if action == "browse":
        return browse_directories(command.get("cwd"))
    if action == "models":
        return list_models()
    if action == "start":
        launch_terminal(Path(command["cwd"]), command.get("mode") or "default", instance_id,
                        command.get("model"), command.get("effort"), command.get("trust_project", False))
        return f"已启动实例 {instance_id}"
    if action == "restart":
        restart_instance(instance_id, command.get("mode"), command.get("model"), command.get("effort"),
                         None)
        return f"已重新启动实例 {instance_id}"
    if action == "trust_project":
        restart_instance(instance_id, command.get("mode"), command.get("model"), command.get("effort"), True)
        return f"已信任项目并重新启动实例 {instance_id}"
    if action == "stop":
        stop_instance(instance_id)
        return f"已停止实例 {instance_id}"
    if action == "delete":
        delete_instance(instance_id)
        return f"已删除历史 {instance_id}"
    if action == "task":
        return send_task(instance_id, command["prompt"])
    if action == "approval":
        return answer_approval(instance_id, command["approval_id"], command["decision"])
    raise ValueError(f"Unsupported command action: {action}")


def _poll_commands(base_url: str, token: str, machine_id: str) -> bool:
    request = Request(base_url + "/api/commands/pending?" + urlencode({"machine_id": machine_id}),
                      headers={"Authorization": f"Bearer {token}"})
    with urlopen(request, timeout=10) as response:
        commands = json.load(response).get("commands", [])
    for command in commands:
        try:
            output = _execute_command(command)
            message = output if isinstance(output, str) else "OK"
            data = output if isinstance(output, dict) else None
            success = True
        except Exception as exc:
            message = str(exc)[:500]
            data = None
            success = False
        result = Request(
            base_url + "/api/commands/" + quote(command["id"], safe="") + "/result",
            data=json.dumps({"machine_id": machine_id, "success": success,
                             "message": message, "data": data}).encode("utf-8"),
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(result, timeout=10) as response:
            response.read()
    return bool(commands)


def _report_loop(args, stop: threading.Event | None = None) -> None:
    if not args.token or not (args.ssh_target or args.local_master):
        raise ValueError("configure a master connection and CODEX_AGENT_HARNESS_REPORT_TOKEN")
    hostname = socket.gethostname()
    machine_id = args.machine_id or _machine_id(_identity_path(hostname))
    tunnel = (SshTunnel(args.ssh_target, args.master_port, args.ssh_port, args.ssh_identity)
              if args.ssh_target else None)
    last_snapshot = None
    last_sent = 0.0
    try:
        while True:
            poll_interval = 2.0
            try:
                if tunnel:
                    tunnel.ensure_running()
                    if args.once:
                        # SSH authentication can take longer than a one-shot report.
                        for _ in range(40):
                            if tunnel.process and tunnel.process.poll() is not None:
                                tunnel.ensure_running()
                            try:
                                with urlopen(tunnel.base_url + "/healthz", timeout=0.5):
                                    break
                            except (HTTPError, URLError, TimeoutError, OSError):
                                time.sleep(0.25)
                snapshot = collect_managed()
                if not args.once:
                    ensure_bridges(snapshot)
                    augment_snapshot(snapshot)
                if any(instance.get("status") in {"working", "attention"}
                       or instance.get("turn_active") or instance.get("live_text")
                       or instance.get("pending_approvals")
                       for instance in snapshot["instances"]):
                    poll_interval = 1.0
                snapshot_key = json.dumps(snapshot, sort_keys=True)
                base_url = tunnel.base_url if tunnel else f"http://127.0.0.1:{args.master_port}"
                # Changes send on the next poll; a full heartbeat refreshes every 20 seconds.
                if args.once or snapshot_key != last_snapshot or time.monotonic() - last_sent >= 20:
                    payload = {
                        "machine_id": machine_id,
                        "hostname": hostname,
                        "platform": platform.system().lower(),
                        "local": bool(args.local_master),
                        **snapshot,
                    }
                    request = Request(
                        base_url + "/api/report",
                        data=json.dumps(payload).encode("utf-8"),
                        headers={"Authorization": f"Bearer {args.token}", "Content-Type": "application/json"},
                        method="POST",
                    )
                    with urlopen(request, timeout=10) as response:
                        response.read()
                    last_snapshot = snapshot_key
                    last_sent = time.monotonic()
                    print(f"reported {len(snapshot['instances'])} managed instances", flush=True)
                if not args.once and _poll_commands(base_url, args.token, machine_id):
                    last_snapshot = None
            except (HTTPError, URLError, TimeoutError, OSError, RuntimeError, ValueError) as exc:
                print(f"report failed: {exc}", file=sys.stderr, flush=True)
                if args.once:
                    raise SystemExit(1) from exc
            if args.once or (stop and stop.wait(poll_interval)):
                return
            if not stop:
                time.sleep(poll_interval)
    finally:
        if tunnel:
            tunnel.close()


def main() -> None:
    saved_connection = connection.load()
    parser = argparse.ArgumentParser(description="Report local Codex CLI state to CodexAgentHarness")
    parser.add_argument("--ssh-target", default=os.getenv("CODEX_AGENT_HARNESS_SSH_TARGET") or saved_connection["ssh_target"],
                        help="Laptop SSH host alias or user@host")
    parser.add_argument("--ssh-identity", default=os.getenv("CODEX_AGENT_HARNESS_SSH_IDENTITY") or saved_connection["ssh_identity"],
                        help="private key file for the Laptop SSH login")
    parser.add_argument("--ssh-port", type=int, default=22, help="Laptop SSH port")
    parser.add_argument("--master-port", type=int, default=8000, help="Laptop loopback API port")
    parser.add_argument("--local-master", action="store_true", help="report to a master on this machine")
    parser.add_argument("--machine-id", default=os.getenv("CODEX_AGENT_HARNESS_MACHINE_ID"),
                        help="stable unique ID for this machine (defaults to a per-host ID file)")
    parser.add_argument("--token", default=os.getenv("CODEX_AGENT_HARNESS_REPORT_TOKEN") or saved_connection["token"],
                        help="report bearer token")
    parser.add_argument("--once", action="store_true", help="send one snapshot and exit")
    parser.add_argument("--headless", action="store_true", help="report without the local window")
    parser.add_argument("--launcher-only", action="store_true",
                        help="open the local launcher while a separate Agent service reports")
    args = parser.parse_args()
    if args.launcher_only and (args.headless or args.once):
        parser.error("--launcher-only cannot be combined with --headless or --once")
    if args.ssh_target and args.local_master:
        parser.error("choose either --ssh-target or --local-master")
    if bool(args.ssh_target or args.local_master) != bool(args.token):
        parser.error("set a master connection and CODEX_AGENT_HARNESS_REPORT_TOKEN together")
    if not 1 <= args.master_port <= 65535 or not 1 <= args.ssh_port <= 65535:
        parser.error("SSH and master ports must be between 1 and 65535")
    if args.ssh_identity and not args.ssh_target:
        parser.error("--ssh-identity requires --ssh-target")
    if args.ssh_target and (args.ssh_target.startswith("-") or any(char.isspace() for char in args.ssh_target)):
        parser.error("SSH target must be a host alias or user@host")
    if args.machine_id is not None and not 1 <= len(args.machine_id) <= 100:
        parser.error("machine ID must be between 1 and 100 characters")
    if (args.headless or args.once) and not args.token:
        parser.error("reporting requires a master connection and report token")
    if args.headless or args.once:
        try:
            _report_loop(args)
        except ValueError as exc:
            parser.error(str(exc))
        return
    from .gui import run_gui
    if args.launcher_only:
        run_gui(reporting=False, external_reporting=True)
        return
    reporter_stop: threading.Event | None = None

    def start_reporter(configured: dict[str, str]) -> None:
        nonlocal reporter_stop
        if reporter_stop:
            reporter_stop.set()
        reporter_stop = None
        if configured["ssh_target"] and configured["token"]:
            current = argparse.Namespace(**vars(args))
            current.ssh_target = configured["ssh_target"]
            current.ssh_identity = configured["ssh_identity"] or None
            current.token = configured["token"]
            current.local_master = False
            reporter_stop = threading.Event()
            threading.Thread(target=_report_loop, args=(current, reporter_stop), daemon=True).start()

    if args.token:
        if args.ssh_target:
            start_reporter({"ssh_target": args.ssh_target, "ssh_identity": args.ssh_identity or "",
                            "token": args.token})
        else:
            reporter_stop = threading.Event()
            threading.Thread(target=_report_loop, args=(args, reporter_stop), daemon=True).start()
    try:
        run_gui(reporting=bool(args.token),
                connection_values={"ssh_target": args.ssh_target or "", "ssh_identity": args.ssh_identity or "",
                                   "token": args.token or ""},
                on_connection_saved=start_reporter if not args.local_master else None)
    finally:
        if reporter_stop:
            reporter_stop.set()


if __name__ == "__main__":
    main()
