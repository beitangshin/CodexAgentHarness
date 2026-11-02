"""Launch and inspect Codex CLI instances owned by this application."""

from __future__ import annotations

import argparse
import base64
import json
import os
import socket
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

import psutil
from websockets.sync.client import connect

from . import local_tools

STATE_DIR = Path.home() / ".codex-agent-harness" / "instances"
SESSION_DIR = Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex"))) / "sessions"
LAUNCH_MODES = ("default", "full_access", "bypass")
REASONING_EFFORTS = ("minimal", "low", "medium", "high", "xhigh", "max", "ultra")
MAX_ACTIVITY_ITEMS = 40
MAX_ACTIVITY_TEXT = 1600


def _mode_flags(mode: str) -> list[str]:
    if mode == "default":
        return []
    if mode == "full_access":
        return ["--sandbox", "danger-full-access", "--ask-for-approval", "on-request"]
    if mode == "bypass":
        return ["--dangerously-bypass-approvals-and-sandbox"]
    raise ValueError(f"Unknown Codex launch mode: {mode}")


def _stamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def _record_path(instance_id: str) -> Path:
    return STATE_DIR / f"{instance_id}.json"


def _write(record: dict) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    path = _record_path(record["id"])
    temporary = path.with_name(f"{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
    temporary.write_text(json.dumps(record), encoding="utf-8")
    os.replace(temporary, path)


def _model_flags(model: str | None, effort: str | None) -> list[str]:
    if model is not None and (not model or len(model) > 100 or any(ch.isspace() for ch in model) or model.startswith("-")):
        raise ValueError("Invalid model ID")
    if effort is not None and effort not in REASONING_EFFORTS:
        raise ValueError("Unsupported reasoning effort")
    return (["--model", model] if model else []) + (["--config", f"model_reasoning_effort={effort}"] if effort else [])


def _codex_executable() -> str:
    return local_tools.require("codex")


def _terminal_command(terminal: str, command: list[str]) -> list[str]:
    name = Path(terminal).name.lower()
    if os.name == "nt":
        if terminal == local_tools.WINDOWS_CONSOLE:
            return command
        if name in {"powershell.exe", "pwsh.exe"}:
            quoted = " ".join("'" + value.replace("'", "''") + "'" for value in command)
            encoded = base64.b64encode(("& " + quoted).encode("utf-16le")).decode("ascii")
            return [terminal, "-NoProfile", "-NoExit", "-EncodedCommand", encoded]
        if name == "wt.exe":
            return [terminal, "-w", "new", "nt", "--", *command]
    else:
        options = {"x-terminal-emulator": ["-e"], "gnome-terminal": ["--"],
                   "konsole": ["-e"], "xfce4-terminal": ["--execute"], "xterm": ["-e"]}
        if name in options:
            return [terminal, *options[name], *command]
    raise ValueError(f"Unsupported terminal program: {terminal}")


def _runner_environment() -> dict[str, str]:
    environment = os.environ.copy()
    for name in ("REPORT_TOKEN", "DASHBOARD_USER", "DASHBOARD_PASSWORD",
                 "CODEX_AGENT_HARNESS_REPORT_TOKEN"):
        environment.pop(name, None)
    if not getattr(sys, "frozen", False):
        source_root = str(Path(__file__).resolve().parent.parent)
        existing = environment.get("PYTHONPATH")
        environment["PYTHONPATH"] = os.pathsep.join(
            part for part in (source_root, existing) if part)
    return environment


def launch_terminal(cwd: Path, mode: str = "default", instance_id: str | None = None,
                    model: str | None = None, effort: str | None = None,
                    trust_project: bool = False) -> str:
    cwd = cwd.expanduser().resolve(strict=True)
    if not cwd.is_dir():
        raise ValueError("Working directory must be a folder")
    _mode_flags(mode)
    _model_flags(model, effort)
    codex = _codex_executable()
    terminal = local_tools.require("terminal")
    if instance_id is None:
        instance_id = str(uuid.uuid4())
    elif str(uuid.UUID(instance_id)) != instance_id:
        raise ValueError("Instance ID must be a canonical UUID")
    if _record_path(instance_id).exists():
        previous = json.loads(_record_path(instance_id).read_text(encoding="utf-8"))
        if any(_alive(previous.get(f"{name}_pid"), previous.get(f"{name}_created"))
               for name in ("cli", "runner", "app_server")):
            raise RuntimeError("Instance is already running")
    command = [sys.executable]
    if not getattr(sys, "frozen", False):
        command.extend(["-m", "codex_agent_harness.managed"])
    command.extend(["run", "--id", instance_id, "--cwd", str(cwd), "--codex", codex,
                    "--mode", mode])
    if model:
        command.extend(["--model", model])
    if effort:
        command.extend(["--effort", effort])
    if trust_project:
        command.append("--trust-project")
    record = {"id": instance_id, "cwd": str(cwd), "state": "starting", "started_at": _stamp(),
              "launch_mode": mode, "model": model, "reasoning_effort": effort,
              "trust_project": trust_project}
    _write(record)
    try:
        subprocess.Popen(_terminal_command(terminal, command), cwd=cwd, env=_runner_environment(),
                         creationflags=subprocess.CREATE_NEW_CONSOLE if os.name == "nt" else 0)
    except Exception:
        _record_path(instance_id).unlink(missing_ok=True)
        raise
    return instance_id


def _read_record(instance_id: str) -> dict:
    if str(uuid.UUID(instance_id)) != instance_id:
        raise ValueError("Instance ID must be a canonical UUID")
    return json.loads(_record_path(instance_id).read_text(encoding="utf-8"))


def _remaining(record: dict) -> list[str]:
    return [name for name in ("cli", "runner", "app_server")
            if _alive(record.get(f"{name}_pid"), record.get(f"{name}_created"))]


def _force_stop(record: dict, names: list[str]) -> None:
    for name in names:
        pid, created = record.get(f"{name}_pid"), record.get(f"{name}_created")
        try:
            process = psutil.Process(pid)
            if process.is_running() and abs(process.create_time() - created) < 1:
                process.kill()
        except (psutil.Error, OSError):
            pass


def _wait_stopped(record: dict, checks: int) -> list[str]:
    for _ in range(checks):
        names = _remaining(record)
        if not names:
            return []
        time.sleep(0.1)
    return _remaining(record)


def restart_instance(instance_id: str, mode: str | None = None,
                     model: str | None | object = ..., effort: str | None | object = ...,
                     trust_project: bool | None = None) -> str:
    record = _read_record(instance_id)
    selected_mode = mode or record.get("launch_mode", "default")
    _mode_flags(selected_mode)
    selected_model = record.get("model") if model is ... else model
    selected_effort = record.get("reasoning_effort") if effort is ... else effort
    selected_trust = record.get("trust_project", False) if trust_project is None else trust_project
    _model_flags(selected_model, selected_effort)
    if trust_project is True:
        _persist_project_trust(Path(record["cwd"]).expanduser().resolve(strict=True), _codex_executable())
    if _remaining(record):
        stop_instance(instance_id)
        still_alive = _wait_stopped(record, 50)
    else:
        still_alive = []
    if still_alive:
        # These PIDs were recorded when this instance was launched. Verify their
        # creation times again before escalating a requested restart.
        _force_stop(record, still_alive)
        still_alive = _wait_stopped(record, 20)
    if still_alive:
        details = ", ".join(f"{name} PID {record.get(f'{name}_pid')}" for name in still_alive)
        raise RuntimeError(f"Managed processes are still running ({details}); restart was cancelled")
    return launch_terminal(Path(record["cwd"]), selected_mode, instance_id, selected_model,
                           selected_effort, selected_trust)


def stop_instance(instance_id: str) -> None:
    record = _read_record(instance_id)
    if record.get("state") == "starting" and not record.get("runner_pid"):
        raise RuntimeError("Instance is still starting; try again shortly")
    for name in ("cli", "runner", "app_server"):
        pid, created = record.get(f"{name}_pid"), record.get(f"{name}_created")
        if not pid or not created:
            continue
        try:
            process = psutil.Process(pid)
            if process.is_running() and abs(process.create_time() - created) < 1:
                process.terminate()
        except (psutil.Error, OSError):
            pass
    record.update({"state": "exited", "ended_at": _stamp()})
    _write(record)


def delete_instance(instance_id: str) -> None:
    record = _read_record(instance_id)
    remaining = _remaining(record)
    if "cli" in remaining:
        raise RuntimeError("Stop the instance before deleting its history")
    if remaining:
        stop_instance(instance_id)
        remaining = _wait_stopped(record, 10)
        if remaining:
            _force_stop(record, remaining)
            remaining = _wait_stopped(record, 20)
        if remaining:
            details = ", ".join(f"{name} PID {record.get(f'{name}_pid')}" for name in remaining)
            raise RuntimeError(f"Cannot delete history while managed processes remain ({details})")
    _record_path(instance_id).unlink()


def delete_exited() -> int:
    count = 0
    if not STATE_DIR.exists():
        return count
    for path in STATE_DIR.glob("*.json"):
        try:
            delete_instance(path.stem)
            count += 1
        except (ValueError, KeyError, OSError, RuntimeError, json.JSONDecodeError):
            continue
    return count


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _ready(port: int, proc: subprocess.Popen) -> None:
    for _ in range(50):
        if proc.poll() is not None:
            raise RuntimeError(f"Codex app-server exited with code {proc.returncode}")
        try:
            with urlopen(f"http://127.0.0.1:{port}/readyz", timeout=0.3):
                return
        except (URLError, TimeoutError, OSError):
            time.sleep(0.2)
    raise RuntimeError("Codex app-server did not become ready")


def _persist_project_trust(cwd: Path, codex: str) -> None:
    """Use Codex's own config API to save exactly this folder's trust decision."""
    port = _free_port()
    proc = subprocess.Popen(
        [codex, "app-server", "--listen", f"ws://127.0.0.1:{port}"],
        cwd=cwd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )
    try:
        _ready(port, proc)
        with connect(f"ws://127.0.0.1:{port}", open_timeout=3, close_timeout=1) as ws:
            _rpc(ws, "initialize", 1, {"clientInfo": {
                "name": "codex_agent_harness", "title": "CodexAgentHarness", "version": "0.1.0"}})
            ws.send(json.dumps({"method": "initialized", "params": {}}))
            key_path = f'projects.{json.dumps(str(cwd), ensure_ascii=False)}.trust_level'
            result = _rpc(ws, "config/batchWrite", 2, {
                "edits": [{"keyPath": key_path, "value": "trusted", "mergeStrategy": "replace"}],
                "reloadUserConfig": True,
            })
            if result.get("status") != "ok":
                raise RuntimeError(f"Codex did not save project trust: {result.get('status')}")
            effective = _rpc(ws, "config/read", 3, {"cwd": str(cwd), "includeLayers": True})
            projects = (effective.get("config") or {}).get("projects") or {}
            expected = str(cwd).casefold() if os.name == "nt" else str(cwd)
            confirmed = any(
                (path.casefold() if os.name == "nt" else path) == expected
                and isinstance(value, dict)
                and value.get("trust_level", value.get("trustLevel")) == "trusted"
                for path, value in projects.items()
            )
            if not confirmed:
                raise RuntimeError("Codex did not confirm the project's trusted configuration")
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()


def run_instance(instance_id: str, cwd: Path, codex: str, mode: str = "default",
                 model: str | None = None, effort: str | None = None,
                 trust_project: bool = False) -> int:
    mode_flags = _mode_flags(mode)
    model_flags = _model_flags(model, effort)
    record = {"id": instance_id, "cwd": str(cwd), "state": "starting", "started_at": _stamp(),
              "runner_pid": os.getpid(), "runner_created": psutil.Process().create_time(),
              "launch_mode": mode, "model": model, "reasoning_effort": effort,
              "trust_project": trust_project}
    app_server = None
    cli = None
    try:
        port = _free_port()
        app_server = subprocess.Popen(
            [codex, "app-server", "--listen", f"ws://127.0.0.1:{port}"],
            cwd=cwd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        record.update({"app_server_pid": app_server.pid,
                       "app_server_created": psutil.Process(app_server.pid).create_time(), "port": port})
        _write(record)
        _ready(port, app_server)
        cli = subprocess.Popen([codex, "--remote", f"ws://127.0.0.1:{port}",
                                "-C", str(cwd), *mode_flags, *model_flags], cwd=cwd)
        record.update({"state": "running", "cli_pid": cli.pid,
                       "cli_created": psutil.Process(cli.pid).create_time()})
        _write(record)
        code = cli.wait()
        record.update({"state": "exited", "exit_code": code, "ended_at": _stamp()})
        _write(record)
        return code
    except Exception as exc:
        record.update({"state": "error", "error": str(exc)[:300], "ended_at": _stamp()})
        _write(record)
        print(f"CodexAgentHarness: {exc}", file=sys.stderr)
        return 1
    finally:
        if cli and cli.poll() is None:
            cli.terminate()
            try:
                cli.wait(timeout=3)
            except subprocess.TimeoutExpired:
                cli.kill()
        if app_server and app_server.poll() is None:
            app_server.terminate()
            try:
                app_server.wait(timeout=3)
            except subprocess.TimeoutExpired:
                app_server.kill()


def _alive(pid: int | None, created: float | None) -> bool:
    if not pid or not created:
        return False
    try:
        proc = psutil.Process(pid)
        return proc.is_running() and proc.status() != psutil.STATUS_ZOMBIE and abs(proc.create_time() - created) < 1
    except (psutil.Error, OSError):
        return False


def _stop_orphan(record: dict) -> None:
    pid = record.get("app_server_pid")
    created = record.get("app_server_created")
    if not pid or not created:
        return
    try:
        proc = psutil.Process(pid)
        if proc.is_running() and abs(proc.create_time() - created) < 1:
            proc.terminate()
    except (psutil.Error, OSError):
        pass


def _rpc(ws, method: str, request_id: int, params: dict | None = None) -> dict:
    ws.send(json.dumps({"method": method, "id": request_id, "params": params or {}}))
    for _ in range(50):
        response = json.loads(ws.recv(timeout=3))
        if response.get("id") == request_id:
            if "error" in response:
                raise RuntimeError(str(response["error"]))
            return response.get("result", {})
    raise RuntimeError(f"No response to {method}")


def browse_directories(path: str | None = None) -> dict:
    folder = Path(path).expanduser() if path else Path.home()
    folder = folder.resolve(strict=True)
    if not folder.is_dir():
        raise ValueError("Selected path is not a directory")
    children = []
    for child in folder.iterdir():
        try:
            if child.is_dir():
                children.append(child.name)
        except OSError:
            continue
    children.sort(key=str.casefold)
    return {"path": str(folder), "parent": str(folder.parent) if folder.parent != folder else None,
            "directories": children[:200], "truncated": len(children) > 200}


def list_models() -> dict:
    """Ask this machine's Codex app-server for its visible model catalog."""
    codex = _codex_executable()
    port = _free_port()
    proc = subprocess.Popen([codex, "app-server", "--listen", f"ws://127.0.0.1:{port}"],
                            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
    try:
        _ready(port, proc)
        with connect(f"ws://127.0.0.1:{port}", open_timeout=3, close_timeout=1) as ws:
            _rpc(ws, "initialize", 1, {"clientInfo": {
                "name": "codex_agent_harness", "title": "CodexAgentHarness", "version": "0.1.0"}})
            ws.send(json.dumps({"method": "initialized", "params": {}}))
            result = _rpc(ws, "model/list", 2, {"limit": 100, "includeHidden": False})
        models = []
        for item in result.get("data") or []:
            model_id = item.get("model") or item.get("id")
            if not model_id or item.get("hidden"):
                continue
            efforts = [entry.get("reasoningEffort") for entry in item.get("supportedReasoningEfforts") or []]
            models.append({"id": model_id, "name": item.get("displayName") or model_id,
                           "efforts": [value for value in efforts if value in REASONING_EFFORTS],
                           "default_effort": item.get("defaultReasoningEffort"),
                           "default": bool(item.get("isDefault"))})
        return {"models": models, "truncated": bool(result.get("nextCursor"))}
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()


def _compact_text(value: object) -> str:
    if isinstance(value, str):
        return value[:MAX_ACTIVITY_TEXT]
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False)[:MAX_ACTIVITY_TEXT]
    return ""


_session_paths: dict[str, Path] = {}
_session_model_cache: dict[str, tuple[int, float, tuple[str | None, str | None]]] = {}


def _latest_turn_model(thread_id: str | None) -> tuple[str | None, str | None]:
    """Read model metadata for an already identified managed thread, never its liveness."""
    if not thread_id or not SESSION_DIR.exists():
        return None, None
    path = _session_paths.get(thread_id)
    if path is None or not path.is_file():
        path = next(SESSION_DIR.rglob(f"*{thread_id}.jsonl"), None)
        if path is None:
            return None, None
        _session_paths[thread_id] = path
    try:
        stat = path.stat()
        cached = _session_model_cache.get(thread_id)
        if cached and cached[:2] == (stat.st_size, stat.st_mtime):
            return cached[2]
        with path.open("rb") as stream:
            stream.seek(max(0, stat.st_size - 2_000_000))
            if stream.tell():
                stream.readline()
            lines = stream.readlines()
        result: tuple[str | None, str | None] = (None, None)
        for raw in reversed(lines):
            try:
                event = json.loads(raw)
            except (ValueError, UnicodeDecodeError):
                continue
            if event.get("type") == "turn_context":
                payload = event.get("payload") or {}
                model = payload.get("model")
                effort = payload.get("effort")
                result = (model if isinstance(model, str) else None,
                          effort if isinstance(effort, str) else None)
                break
        _session_model_cache[thread_id] = (stat.st_size, stat.st_mtime, result)
        return result
    except OSError:
        return None, None


def _activity_item(item: dict) -> dict | None:
    kind = item.get("type")
    label = {
        "userMessage": "用户", "agentMessage": "Codex", "commandExecution": "命令",
        "fileChange": "文件变更", "plan": "计划", "reasoning": "思考摘要",
        "mcpToolCall": "工具", "webSearch": "搜索",
    }.get(kind)
    if not label:
        return None
    if kind == "userMessage":
        content = item.get("content") or []
        value = "\n".join(part.get("text", "") for part in content
                          if isinstance(part, dict) and part.get("type") == "text")
    elif kind == "agentMessage":
        value = item.get("text", "")
    elif kind == "commandExecution":
        value = "$ " + str(item.get("command") or "")
        if item.get("aggregatedOutput"):
            value += "\n" + str(item["aggregatedOutput"])
    elif kind == "fileChange":
        value = "\n".join(f"{change.get('kind', 'change')}: {change.get('path', '')}\n{change.get('diff', '')}"
                          for change in (item.get("changes") or []) if isinstance(change, dict))
    elif kind == "reasoning":
        summary = item.get("summary") or []
        value = "\n".join(part.get("text", "") if isinstance(part, dict) else str(part)
                          for part in summary)
    elif kind == "mcpToolCall":
        value = f"{item.get('server', '')}/{item.get('tool', '')}"
        if item.get("arguments"):
            value += "\n" + _compact_text(item["arguments"])
    else:
        value = item.get("text") or item.get("query") or ""
    text = _compact_text(value).strip()
    if not text:
        return None
    return {"kind": label, "text": text, "status": str(item.get("status") or "")[:40]}


def _recent_activity(ws, thread_id: str) -> list[dict]:
    items = []
    try:
        result = _rpc(ws, "thread/items/list", 100, {
            "threadId": thread_id, "sortDirection": "desc", "limit": MAX_ACTIVITY_ITEMS,
        })
        items = [entry.get("item", entry) for entry in reversed(result.get("data") or [])
                 if isinstance(entry, dict)]
    except RuntimeError:
        pass
    if not items:
        try:
            result = _rpc(ws, "thread/turns/list", 101, {
                "threadId": thread_id, "sortDirection": "desc", "limit": 2,
                "itemsView": "full",
            })
            turns = list(reversed(result.get("data") or []))
        except RuntimeError:
            turns = []
        items = [item for entry in turns if isinstance(entry, dict)
                 for item in (entry.get("turn", entry).get("items") or [])]
    if not items:
        try:
            result = _rpc(ws, "thread/read", 102, {
                "threadId": thread_id, "includeTurns": True,
            })
            turns = (result.get("thread") or {}).get("turns") or []
        except RuntimeError:
            return []
        items = [item for entry in turns if isinstance(entry, dict)
                 for item in (entry.get("turn", entry).get("items") or [])]
    activity = [_activity_item(item) for item in items if isinstance(item, dict)]
    return [entry for entry in activity if entry][-MAX_ACTIVITY_ITEMS:]


def send_task(instance_id: str, prompt: str) -> str:
    if not prompt.strip():
        raise ValueError("Task must not be empty")
    record = _read_record(instance_id)
    if not (_alive(record.get("cli_pid"), record.get("cli_created"))
            and _alive(record.get("app_server_pid"), record.get("app_server_created"))):
        raise RuntimeError("Codex instance is not running")
    with connect(f"ws://127.0.0.1:{record['port']}", open_timeout=2, close_timeout=1) as ws:
        _rpc(ws, "initialize", 1, {"clientInfo": {
            "name": "codex_agent_harness", "title": "CodexAgentHarness", "version": "0.1.0"}})
        ws.send(json.dumps({"method": "initialized", "params": {}}))
        loaded = _rpc(ws, "thread/loaded/list", 2).get("data") or []
        if not loaded:
            raise RuntimeError("Codex thread is not ready; try again shortly")
        threads = []
        for request_id, thread_id in enumerate(sorted(loaded), start=3):
            thread = _rpc(ws, "thread/read", request_id, {"threadId": thread_id}).get("thread")
            if thread:
                threads.append(thread)
        current = max(threads, key=lambda thread: thread.get("updatedAt") or 0, default=None)
        if not current:
            raise RuntimeError("Codex thread is not available")
        thread_id = current["id"]
        task_input = [{"type": "text", "text": prompt.strip()}]
        if (current.get("status") or {}).get("type") == "active":
            try:
                turns = _rpc(ws, "thread/turns/list", 100, {
                    "threadId": thread_id, "sortDirection": "desc", "limit": 1,
                    "itemsView": "notLoaded",
                }).get("data") or []
            except RuntimeError:
                turns = []
            if not turns:
                history = _rpc(ws, "thread/read", 102, {
                    "threadId": thread_id, "includeTurns": True,
                }).get("thread") or {}
                turns = history.get("turns") or []
                turns = turns[-1:]
            turn = turns[0].get("turn", turns[0]) if turns else {}
            turn_id = turn.get("id")
            if not turn_id:
                raise RuntimeError("Active Codex turn ID is unavailable; try again when idle")
            _rpc(ws, "turn/steer", 101, {"threadId": thread_id, "input": task_input,
                                         "expectedTurnId": turn_id})
            return "Task sent to active Codex turn"
        _rpc(ws, "turn/start", 101, {"threadId": thread_id, "input": task_input})
        return "Task sent to Codex"


def _thread_state(port: int, preferred_thread_id: str | None = None) -> tuple[str, str | None, str | None, list[dict]]:
    with connect(f"ws://127.0.0.1:{port}", open_timeout=2, close_timeout=1) as ws:
        _rpc(ws, "initialize", 1, {"clientInfo": {
            "name": "codex_agent_harness", "title": "CodexAgentHarness", "version": "0.1.0"}})
        ws.send(json.dumps({"method": "initialized", "params": {}}))
        loaded = set(_rpc(ws, "thread/loaded/list", 2).get("data", []))
        if not loaded:
            return "idle", None, None, []
        threads = []
        for request_id, thread_id in enumerate(sorted(loaded), start=3):
            thread = _rpc(ws, "thread/read", request_id, {"threadId": thread_id}).get("thread")
            if thread:
                threads.append(thread)
        active_threads = [thread for thread in threads
                          if (thread.get("status") or {}).get("type") == "active"]
        preferred = next((thread for thread in threads
                          if thread.get("id") == preferred_thread_id), None)
        if preferred in active_threads:
            current = preferred
        elif active_threads:
            current = max(active_threads, key=lambda thread: thread.get("updatedAt") or 0)
        else:
            current = max(threads, key=lambda thread: thread.get("updatedAt") or 0,
                          default=None)
        if not current:
            return "unknown", None, None, []
        runtime = current.get("status") or {}
        kind = runtime.get("type")
        flags = runtime.get("activeFlags") or []
        if kind == "active":
            status = "attention" if any("waiting" in flag.lower() for flag in flags) else "working"
        elif kind == "idle":
            status = "idle"
        elif kind == "systemError":
            status = "error"
        else:
            status = "unknown"
        updated = current.get("updatedAt")
        observed = datetime.fromtimestamp(updated, timezone.utc).isoformat() if isinstance(updated, (int, float)) else None
        thread_id = current.get("id")
        activity = _recent_activity(ws, thread_id) if thread_id else []
        return status, thread_id, observed, activity


_external_scan_at = 0.0
_external_cache: list[tuple[dict, float]] = []


def _external_cli_instances(excluded_pids: set[int]) -> list[dict]:
    """Show Windows Codex CLI processes not launched by this Harness."""
    if os.name != "nt":
        return []
    global _external_scan_at, _external_cache
    if time.monotonic() - _external_scan_at < 10:
        return [row.copy() for row, created in _external_cache
                if row["pid"] not in excluded_pids and _alive(row["pid"], created)]
    found: list[tuple[dict, float]] = []
    for process in psutil.process_iter(attrs=["pid", "name"], ad_value=None):
        try:
            info = process.info
            pid = info.get("pid")
            if not pid or pid in excluded_pids or (info.get("name") or "").lower() != "codex.exe":
                continue
            command = process.cmdline()
            if not command or any("app-server" in str(arg).lower() for arg in command[1:]):
                continue
            created = process.create_time()
            if not isinstance(created, (int, float)):
                continue
            cwd = process.cwd()
            if not cwd:
                continue
            found.append(({
                "id": f"external-{pid}-{int(created * 1000)}",
                "project": Path(cwd).name or cwd,
                "cwd": cwd,
                "status": "unknown",
                "confidence": "unconfirmed",
                "pid": pid,
                "last_activity": datetime.fromtimestamp(created, timezone.utc).isoformat(),
                "last_state_event": None,
                "launch_mode": "default",
                "managed": False,
                "activity": [],
                "pending_approvals": [],
            }, created))
        except (psutil.Error, OSError, ValueError):
            continue
    _external_cache = found
    _external_scan_at = time.monotonic()
    return [row.copy() for row, _ in found]


def collect_managed() -> dict:
    now = time.time()
    instances = []
    live_count = 0
    tracked_live_pids: set[int] = set()
    if STATE_DIR.exists():
        for path in STATE_DIR.glob("*.json"):
            try:
                record = json.loads(path.read_text(encoding="utf-8"))
                started = datetime.fromisoformat(record["started_at"]).timestamp()
            except (OSError, ValueError, KeyError, TypeError):
                continue
            cli_alive = _alive(record.get("cli_pid"), record.get("cli_created"))
            if cli_alive and record.get("cli_pid"):
                tracked_live_pids.add(record["cli_pid"])
            server_alive = _alive(record.get("app_server_pid"), record.get("app_server_created"))
            runner_alive = _alive(record.get("runner_pid"), record.get("runner_created"))
            if server_alive and not cli_alive and not runner_alive:
                _stop_orphan(record)
                server_alive = False
            if not cli_alive and not runner_alive and "ended_at" not in record:
                if record.get("state") == "running" or now - started >= 30:
                    failed_to_start = not record.get("cli_pid")
                    record.update({"state": "error" if failed_to_start else "exited",
                                   "ended_at": _stamp()})
                    if failed_to_start:
                        record.setdefault("error", "Runner exited before it registered a Codex process")
                    _write(record)
            status = "starting" if record.get("state") == "starting" and (runner_alive or now - started < 30) else "exited"
            thread_id = record.get("thread_id")
            observed = None
            activity = []
            if cli_alive and server_alive:
                live_count += 1
                try:
                    status, loaded_thread_id, observed, activity = _thread_state(
                        record["port"], thread_id)
                    if loaded_thread_id and loaded_thread_id != thread_id:
                        thread_id = loaded_thread_id
                        record["thread_id"] = thread_id
                        _write(record)
                except Exception:
                    status = "unknown"
            elif cli_alive:
                live_count += 1
                status = "error"
            elif record.get("state") == "error":
                status = "error"
            active_model, active_effort = _latest_turn_model(thread_id)
            instance = {
                "id": record["id"], "thread_id": thread_id,
                "project": Path(record["cwd"]).name or record["cwd"],
                "cwd": record["cwd"],
                "launch_mode": record.get("launch_mode", "default"),
                "trust_project": record.get("trust_project", False),
                "managed": True,
                "model": record.get("model"), "reasoning_effort": record.get("reasoning_effort"),
                "active_model": active_model, "active_reasoning_effort": active_effort,
                "status": status, "confidence": "confirmed", "pid": record.get("cli_pid") or record.get("runner_pid"),
                "error": record.get("error") or (
                    "Runner exited before it registered a Codex process"
                    if status == "error" and not record.get("cli_pid") else None),
                "last_activity": observed or record.get("ended_at") or record["started_at"],
                "last_state_event": observed,
                "activity": activity,
                "pending_approvals": [],
            }
            instances.append(instance)
    external = _external_cli_instances(tracked_live_pids)
    instances.extend(external)
    live_count += len(external)
    instances.sort(key=lambda row: row["last_activity"], reverse=True)
    return {"cli_process_count": live_count, "instances": instances}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["run"])
    parser.add_argument("--id", required=True)
    parser.add_argument("--cwd", type=Path, required=True)
    parser.add_argument("--codex", required=True)
    parser.add_argument("--mode", choices=LAUNCH_MODES, default="default")
    parser.add_argument("--model")
    parser.add_argument("--effort", choices=REASONING_EFFORTS)
    parser.add_argument("--trust-project", action="store_true")
    args = parser.parse_args()
    raise SystemExit(run_instance(args.id, args.cwd, args.codex, args.mode, args.model,
                                  args.effort, args.trust_project))


if __name__ == "__main__":
    main()
