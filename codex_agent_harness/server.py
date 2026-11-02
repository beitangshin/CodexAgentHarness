from __future__ import annotations

import os
import secrets
import socket
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import FileResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import BaseModel, Field
import psutil

from . import local_tools


class Activity(BaseModel):
    kind: str = Field(max_length=40)
    text: str = Field(max_length=1600)
    status: str = Field(default="", max_length=40)


class PendingApproval(BaseModel):
    id: str = Field(min_length=1, max_length=100)
    kind: Literal["command", "file"]
    source: Literal["master", "terminal"] = "master"
    thread_id: str = Field(default="", max_length=100)
    turn_id: str = Field(default="", max_length=100)
    item_id: str = Field(default="", max_length=100)
    reason: str = Field(default="", max_length=1200)
    command: str = Field(default="", max_length=2000)
    cwd: str = Field(default="", max_length=1000)
    available_decisions: list[str] = Field(default_factory=list, max_length=8)


class Instance(BaseModel):
    id: str = Field(min_length=1, max_length=100)
    managed: bool = True
    project: str = Field(max_length=200)
    cwd: str | None = Field(default=None, max_length=1000)
    status: str = Field(pattern="^(starting|working|idle|attention|unknown|exited|error)$")
    confidence: str = Field(pattern="^(confirmed|inferred|unconfirmed)$")
    thread_id: str | None = Field(default=None, max_length=100)
    pid: int | None = Field(default=None, ge=1)
    error: str | None = Field(default=None, max_length=300)
    last_activity: datetime
    last_state_event: datetime | None = None
    launch_mode: str = Field(default="default", pattern="^(default|full_access|bypass)$")
    trust_project: bool = False
    model: str | None = Field(default=None, max_length=100)
    reasoning_effort: str | None = Field(default=None, max_length=20)
    active_model: str | None = Field(default=None, max_length=100)
    active_reasoning_effort: str | None = Field(default=None, max_length=20)
    activity: list[Activity] = Field(default_factory=list, max_length=40)
    pending_approvals: list[PendingApproval] = Field(default_factory=list, max_length=10)
    live_text: str = Field(default="", max_length=4000)
    turn_active: bool = False
    interaction_ready: bool = False


class Report(BaseModel):
    machine_id: str = Field(min_length=1, max_length=100)
    hostname: str = Field(min_length=1, max_length=200)
    platform: str = Field(max_length=40)
    local: bool = False
    cli_process_count: int = Field(ge=0)
    instances: list[Instance] = Field(max_length=500)


class CommandRequest(BaseModel):
    machine_id: str = Field(min_length=1, max_length=100)
    action: Literal["start", "stop", "restart", "trust_project", "delete", "task", "approval", "browse", "models"]
    instance_id: str | None = Field(default=None, max_length=100)
    cwd: str | None = Field(default=None, max_length=1000)
    mode: Literal["default", "full_access", "bypass"] | None = None
    model: str | None = Field(default=None, max_length=100)
    effort: Literal["minimal", "low", "medium", "high", "xhigh", "max", "ultra"] | None = None
    prompt: str | None = Field(default=None, max_length=8000)
    approval_id: str | None = Field(default=None, max_length=100)
    decision: Literal["accept", "acceptForSession", "decline", "cancel"] | None = None


class CommandResult(BaseModel):
    machine_id: str = Field(min_length=1, max_length=100)
    success: bool
    message: str = Field(default="", max_length=500)
    data: dict | None = None


class LocalToolsRequest(BaseModel):
    codex: str = Field(default="", max_length=1000)
    terminal: str = Field(default="", max_length=1000)
    ssh: str = Field(default="", max_length=1000)


app = FastAPI(title="CodexAgentHarness", docs_url=None, redoc_url=None)
basic = HTTPBasic()
_lock = threading.Lock()
_machines: dict[str, dict] = {}
_commands: dict[str, dict] = {}


def _dashboard_auth(credentials: HTTPBasicCredentials = Depends(basic)) -> None:
    expected_user = os.getenv("DASHBOARD_USER")
    expected_password = os.getenv("DASHBOARD_PASSWORD")
    if not expected_user or not expected_password:
        raise HTTPException(status_code=503, detail="Dashboard credentials are not configured")
    if not (secrets.compare_digest(credentials.username, expected_user)
            and secrets.compare_digest(credentials.password, expected_password)):
        raise HTTPException(status_code=401, headers={"WWW-Authenticate": "Basic"})


def _agent_auth(authorization: str | None) -> None:
    expected = os.getenv("REPORT_TOKEN")
    if not expected:
        raise HTTPException(status_code=503, detail="Report token is not configured")
    supplied = authorization.removeprefix("Bearer ") if authorization else ""
    if not secrets.compare_digest(supplied, expected):
        raise HTTPException(status_code=401, detail="Invalid report token")


@app.post("/api/report", status_code=204)
def report_status(report: Report, authorization: str | None = Header(default=None)) -> None:
    _agent_auth(authorization)
    with _lock:
        _machines[report.machine_id] = {
            **report.model_dump(mode="json"),
            "received_at": datetime.now(timezone.utc).isoformat(),
            "received_monotonic": time.monotonic(),
        }


@app.get("/api/status", dependencies=[Depends(_dashboard_auth)])
def get_status() -> dict:
    now = time.monotonic()
    with _lock:
        for command in _commands.values():
            if command["status"] == "dispatched" and now - command["dispatched_monotonic"] > 60:
                command.update({"status": "failed", "message": "Agent 未返回执行结果",
                                "updated_at": datetime.now(timezone.utc).isoformat()})
        machines = [
            {k: v for k, v in machine.items() if k != "received_monotonic"} | {
                "online": now - machine["received_monotonic"] <= 45,
            }
            for machine in _machines.values()
        ]
        commands = [{k: v for k, v in command.items() if k not in {"dispatched_monotonic", "prompt"}}
                    for command in list(_commands.values())[-100:]]
    machines.sort(key=lambda machine: machine["hostname"].lower())
    return {"machines": machines, "commands": commands,
            "server_time": datetime.now(timezone.utc).isoformat()}


@app.post("/api/commands", status_code=202, dependencies=[Depends(_dashboard_auth)])
def create_command(request: CommandRequest) -> dict:
    if request.action == "start" and not request.cwd:
        raise HTTPException(status_code=422, detail="Start requires a working directory")
    if request.action not in {"start", "browse", "models"} and not request.instance_id:
        raise HTTPException(status_code=422, detail="An instance ID is required")
    if request.action == "task" and not (request.prompt and request.prompt.strip()):
        raise HTTPException(status_code=422, detail="Task text is required")
    if request.action == "approval" and not (request.approval_id and request.decision):
        raise HTTPException(status_code=422, detail="Approval ID and decision are required")
    if request.instance_id and not request.instance_id.startswith("external-"):
        try:
            if str(uuid.UUID(request.instance_id)) != request.instance_id:
                raise ValueError
        except ValueError:
            raise HTTPException(status_code=422, detail="Invalid instance ID") from None
    with _lock:
        machine = _machines.get(request.machine_id)
        if not machine:
            raise HTTPException(status_code=404, detail="Machine not found")
        if time.monotonic() - machine["received_monotonic"] > 45:
            raise HTTPException(status_code=409, detail="Machine is offline")
        instance = next((item for item in machine["instances"]
                         if item["id"] == request.instance_id), None)
        if request.action not in {"start", "browse", "models"} and not instance:
            raise HTTPException(status_code=404, detail="Instance not found")
        if instance and not instance.get("managed", True):
            raise HTTPException(status_code=409, detail="External Codex CLI processes are read-only")
        if request.action == "task" and instance["status"] in {"exited", "error", "starting"}:
            raise HTTPException(status_code=409, detail="Instance is not ready for a task")
        if request.action == "approval" and not any(
                item["id"] == request.approval_id
                for item in instance.get("pending_approvals", [])):
            raise HTTPException(status_code=409, detail="Approval is no longer pending")
        command_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        command = {"id": command_id, "machine_id": request.machine_id,
                   "action": request.action,
                   "instance_id": request.instance_id or str(uuid.uuid4()),
                   "cwd": request.cwd if request.action in {"start", "browse"} else None,
                   "mode": (request.mode or "default") if request.action == "start" else
                           request.mode if request.action in {"restart", "trust_project"} else None,
                   "model": request.model if request.action in {"start", "restart", "trust_project"} else None,
                   "effort": request.effort if request.action in {"start", "restart", "trust_project"} else None,
                   "prompt": request.prompt.strip() if request.action == "task" else None,
                   "approval_id": request.approval_id if request.action == "approval" else None,
                   "decision": request.decision if request.action == "approval" else None,
                   "status": "queued", "message": "", "requested_at": now,
                   "updated_at": now}
        _commands[command_id] = command
        if len(_commands) > 200:
            _commands.pop(next(iter(_commands)))
    return {k: v for k, v in command.items() if k != "prompt"}


@app.get("/api/commands/pending")
def pending_commands(machine_id: str, authorization: str | None = Header(default=None)) -> dict:
    _agent_auth(authorization)
    with _lock:
        selected = [command for command in _commands.values()
                    if command["machine_id"] == machine_id and command["status"] == "queued"]
        now = datetime.now(timezone.utc).isoformat()
        for command in selected:
            command["status"] = "dispatched"
            command["updated_at"] = now
            command["dispatched_monotonic"] = time.monotonic()
        return {"commands": [{k: v for k, v in command.items() if k != "dispatched_monotonic"}
                             for command in selected]}


@app.post("/api/commands/{command_id}/result", status_code=204)
def finish_command(command_id: str, result: CommandResult,
                   authorization: str | None = Header(default=None)) -> None:
    _agent_auth(authorization)
    with _lock:
        command = _commands.get(command_id)
        if not command or command["machine_id"] != result.machine_id:
            raise HTTPException(status_code=404, detail="Command not found")
        if command["status"] not in {"dispatched", "succeeded", "failed"}:
            raise HTTPException(status_code=409, detail="Command was not dispatched")
        command["status"] = "succeeded" if result.success else "failed"
        command["message"] = result.message
        if command["action"] in {"browse", "models"}:
            command["data"] = result.data
        command["updated_at"] = datetime.now(timezone.utc).isoformat()


@app.get("/api/master-info", dependencies=[Depends(_dashboard_auth)])
def get_master_info() -> dict:
    interfaces = psutil.net_if_addrs()
    active = psutil.net_if_stats()
    addresses = [
        {"interface": name, "address": address.address}
        for name, values in interfaces.items()
        if active.get(name) and active[name].isup
        for address in values
        if address.family == socket.AF_INET
        and not address.address.startswith(("127.", "169.254."))
    ]
    addresses.sort(key=lambda item: (not item["address"].startswith("10."), item["interface"], item["address"]))
    try:
        with socket.create_connection(("127.0.0.1", 22), timeout=0.2):
            ssh_available = True
    except OSError:
        ssh_available = False
    return {"hostname": socket.gethostname(), "addresses": addresses, "ssh_available": ssh_available}


@app.get("/api/local-tools", dependencies=[Depends(_dashboard_auth)])
def get_local_tools() -> dict:
    configured = local_tools.auto_configure()
    return {"configured": configured,
            "missing": local_tools.missing(),
            "suggestions": {kind: local_tools.suggestions(kind) for kind in local_tools.KINDS}}


@app.put("/api/local-tools", dependencies=[Depends(_dashboard_auth)])
def set_local_tools(request: LocalToolsRequest) -> dict:
    try:
        configured = local_tools.save(request.model_dump())
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"configured": configured}


@app.get("/", dependencies=[Depends(_dashboard_auth)])
def dashboard() -> FileResponse:
    return FileResponse(Path(__file__).parent / "static" / "index.html")


@app.get("/healthz")
def health() -> dict:
    return {"ok": True}
