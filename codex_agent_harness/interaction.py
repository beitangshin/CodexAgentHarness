"""Long-lived local app-server connections for Master-initiated turns and approvals."""

from __future__ import annotations

import json
import queue
import threading
import time
import uuid

from websockets.exceptions import ConnectionClosed
from websockets.sync.client import connect

from .managed import _alive, _read_record


_registry_lock = threading.Lock()
_bridges: dict[str, "InteractionBridge"] = {}
_APPROVAL_METHODS = {
    "item/commandExecution/requestApproval": "command",
    "item/fileChange/requestApproval": "file",
}
_DECISIONS = {"accept", "acceptForSession", "decline", "cancel"}


class InteractionBridge:
    def __init__(self, instance_id: str, port: int) -> None:
        self.instance_id = instance_id
        self.port = port
        self.stop_event = threading.Event()
        self.ready = threading.Event()
        self.lock = threading.Lock()
        self.outbox: queue.Queue[dict] = queue.Queue()
        self.pending: dict[str, dict] = {}
        self.live_text = ""
        self.turn_active = False
        self.recent_activity: list[dict] = []
        self.thread_id: str | None = None
        self.error = ""
        self._next_id = 1000
        self.worker = threading.Thread(target=self._run, daemon=True,
                                       name=f"codex-bridge-{instance_id[:8]}")
        self.worker.start()

    def stop(self) -> None:
        self.stop_event.set()

    def snapshot(self) -> dict:
        with self.lock:
            approvals = [{k: v for k, v in item.items() if k != "request_id"}
                         for item in self.pending.values()]
            return {"pending_approvals": approvals[:10],
                    "live_text": self.live_text[-4000:],
                    "activity": list(self.recent_activity),
                    "turn_active": self.turn_active,
                    "interaction_ready": self.ready.is_set()}

    def _remember(self, kind: str, text: str) -> None:
        text = text.strip()[:1600]
        if not text:
            return
        with self.lock:
            entry = {"kind": kind, "text": text, "status": ""}
            if not self.recent_activity or self.recent_activity[-1] != entry:
                self.recent_activity = (self.recent_activity + [entry])[-40:]

    def submit(self, kind: str, **payload) -> str:
        if not self.ready.wait(timeout=8):
            raise RuntimeError(self.error or "Codex interaction connection is not ready")
        done = threading.Event()
        request = {"kind": kind, "done": done, **payload}
        self.outbox.put(request)
        if not done.wait(timeout=12):
            raise RuntimeError("Codex interaction request timed out")
        if request.get("error"):
            raise RuntimeError(request["error"])
        return request.get("result", "")

    def _call(self, ws, method: str, params: dict | None = None) -> dict:
        self._next_id += 1
        request_id = self._next_id
        ws.send(json.dumps({"id": request_id, "method": method, "params": params or {}}))
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline and not self.stop_event.is_set():
            try:
                message = json.loads(ws.recv(timeout=0.5))
            except TimeoutError:
                continue
            if message.get("id") == request_id and "method" not in message:
                if "error" in message:
                    raise RuntimeError(str(message["error"]))
                return message.get("result") or {}
            self._handle(ws, message)
        raise RuntimeError(f"No response to {method}")

    def _handle(self, ws, message: dict) -> None:
        method = message.get("method")
        params = message.get("params") or {}
        if method in _APPROVAL_METHODS and "id" in message:
            approval_id = uuid.uuid4().hex
            raw_command = params.get("command") or ""
            command = raw_command if isinstance(raw_command, str) else json.dumps(raw_command)
            approval = {
                "id": approval_id, "request_id": message["id"],
                "kind": _APPROVAL_METHODS[method],
                "source": "master",
                "thread_id": str(params.get("threadId") or "")[:100],
                "turn_id": str(params.get("turnId") or "")[:100],
                "item_id": str(params.get("itemId") or "")[:100],
                "reason": str(params.get("reason") or "")[:1200],
                "command": command[:2000],
                "cwd": str(params.get("cwd") or "")[:1000],
                "available_decisions": [str(value) for value in
                                        (params.get("availableDecisions") or [])][:8],
            }
            with self.lock:
                self.pending[approval_id] = approval
            return
        if method == "serverRequest/resolved":
            resolved_id = params.get("requestId")
            with self.lock:
                for key, approval in list(self.pending.items()):
                    if approval["request_id"] == resolved_id:
                        del self.pending[key]
            return
        if method == "turn/started":
            with self.lock:
                self.live_text = ""
                self.turn_active = True
            return
        if method == "item/agentMessage/delta":
            delta = params.get("delta")
            if isinstance(delta, str):
                with self.lock:
                    self.live_text = (self.live_text + delta)[-4000:]
            return
        if method == "item/completed":
            item = params.get("item") or {}
            if item.get("type") == "agentMessage":
                text = item.get("text")
                if isinstance(text, str):
                    self._remember("Codex", text)
                    with self.lock:
                        self.live_text = ""
            return
        if method == "turn/completed":
            with self.lock:
                completed_text = self.live_text
                self.live_text = ""
                self.turn_active = False
            self._remember("Codex", completed_text)

    def _perform(self, ws, request: dict) -> None:
        kind = request["kind"]
        if kind == "approval":
            with self.lock:
                approval = self.pending.get(request["approval_id"])
            if not approval:
                raise RuntimeError("Approval has expired or belongs to the local terminal")
            decision = request["decision"]
            if decision not in _DECISIONS:
                raise ValueError("Unsupported approval decision")
            ws.send(json.dumps({"id": approval["request_id"],
                                "result": {"decision": decision}}))
            with self.lock:
                self.pending.pop(request["approval_id"], None)
            request["result"] = "Approval response sent to Codex"
            return
        if kind == "task":
            thread_id = self.thread_id
            if not thread_id:
                raise RuntimeError("Codex thread is not ready")
            current = self._call(ws, "thread/read", {"threadId": thread_id}).get("thread") or {}
            user_input = [{"type": "text", "text": request["prompt"].strip()}]
            if (current.get("status") or {}).get("type") == "active":
                try:
                    turns = self._call(ws, "thread/turns/list", {
                        "threadId": thread_id, "sortDirection": "desc", "limit": 1,
                        "itemsView": "notLoaded"}).get("data") or []
                except RuntimeError:
                    turns = []
                if not turns:
                    history = self._call(ws, "thread/read", {
                        "threadId": thread_id, "includeTurns": True}).get("thread") or {}
                    turns = (history.get("turns") or [])[-1:]
                turn = turns[0].get("turn", turns[0]) if turns else {}
                if not turn.get("id"):
                    raise RuntimeError("Active turn ID is unavailable; try again when idle")
                self._call(ws, "turn/steer", {"threadId": thread_id,
                                              "input": user_input,
                                              "expectedTurnId": turn["id"]})
                self._remember("用户", request["prompt"])
                request["result"] = "Task sent to active Codex turn"
            else:
                self._call(ws, "turn/start", {"threadId": thread_id,
                                              "input": user_input})
                self._remember("用户", request["prompt"])
                request["result"] = "Task sent to Codex"
            return
        raise ValueError(f"Unsupported interaction request: {kind}")

    def _run(self) -> None:
        while not self.stop_event.is_set():
            try:
                with connect(f"ws://127.0.0.1:{self.port}", open_timeout=2,
                             close_timeout=1) as ws:
                    self._call(ws, "initialize", {"clientInfo": {
                        "name": "codex_agent_harness", "title": "CodexAgentHarness",
                        "version": "0.1.0"}})
                    ws.send(json.dumps({"method": "initialized", "params": {}}))
                    loaded = self._call(ws, "thread/loaded/list").get("data") or []
                    if not loaded:
                        raise RuntimeError("Waiting for Codex thread")
                    threads = []
                    for thread_id in loaded:
                        thread = self._call(ws, "thread/read", {"threadId": thread_id}).get("thread")
                        if thread:
                            threads.append(thread)
                    active_threads = [row for row in threads
                                      if (row.get("status") or {}).get("type") == "active"]
                    current = max(active_threads or threads,
                                  key=lambda row: row.get("updatedAt") or 0, default=None)
                    if not current:
                        raise RuntimeError("Waiting for Codex thread")
                    self.thread_id = current["id"]
                    self.error = ""
                    self.ready.set()
                    while not self.stop_event.is_set():
                        try:
                            request = self.outbox.get_nowait()
                        except queue.Empty:
                            request = None
                        if request:
                            try:
                                self._perform(ws, request)
                            except Exception as exc:
                                request["error"] = str(exc)[:500]
                            finally:
                                request["done"].set()
                        try:
                            self._handle(ws, json.loads(ws.recv(timeout=0.3)))
                        except TimeoutError:
                            pass
            except (OSError, RuntimeError, ConnectionClosed, ValueError) as exc:
                self.error = str(exc)[:300]
            finally:
                self.ready.clear()
                with self.lock:
                    self.pending.clear()
                    self.live_text = ""
                    self.turn_active = False
                while True:
                    try:
                        request = self.outbox.get_nowait()
                    except queue.Empty:
                        break
                    request["error"] = self.error or "Codex connection closed"
                    request["done"].set()
            if not self.stop_event.is_set():
                self.stop_event.wait(1)


def ensure_bridges(snapshot: dict) -> None:
    live = {item["id"]: item for item in snapshot["instances"]
            if item["status"] not in {"exited", "error"}}
    with _registry_lock:
        for instance_id, bridge in list(_bridges.items()):
            if instance_id not in live:
                bridge.stop()
                del _bridges[instance_id]
        for instance_id in live:
            try:
                record = _read_record(instance_id)
                if not _alive(record.get("app_server_pid"), record.get("app_server_created")):
                    continue
                port = record["port"]
            except (OSError, KeyError, ValueError):
                continue
            existing = _bridges.get(instance_id)
            observed_thread = live[instance_id].get("thread_id")
            if (existing and existing.port == port and existing.worker.is_alive()
                    and not (existing.thread_id and observed_thread
                             and existing.thread_id != observed_thread)):
                continue
            if existing:
                existing.stop()
            _bridges[instance_id] = InteractionBridge(instance_id, port)


def augment_snapshot(snapshot: dict) -> None:
    with _registry_lock:
        bridges = dict(_bridges)
    for instance in snapshot["instances"]:
        bridge = bridges.get(instance["id"])
        if bridge:
            bridge_state = bridge.snapshot()
            instance["pending_approvals"] = (
                instance.get("pending_approvals", []) + bridge_state.pop("pending_approvals", [])
            )[:10]
            bridge_activity = bridge_state.pop("activity", [])
            activity = list(instance.get("activity", []))
            known = {(item.get("kind"), item.get("text")) for item in activity}
            for item in bridge_activity:
                key = (item.get("kind"), item.get("text"))
                if key not in known:
                    activity.append(item)
                    known.add(key)
            instance["activity"] = activity[-40:]
            instance.update(bridge_state)
            if instance["pending_approvals"]:
                instance["status"] = "attention"
            elif bridge_state.get("turn_active"):
                instance["status"] = "working"


def send_task(instance_id: str, prompt: str) -> str:
    if not prompt.strip():
        raise ValueError("Task must not be empty")
    with _registry_lock:
        bridge = _bridges.get(instance_id)
    if not bridge:
        raise RuntimeError("Codex interaction connection is not ready")
    return bridge.submit("task", prompt=prompt)


def answer_approval(instance_id: str, approval_id: str, decision: str) -> str:
    with _registry_lock:
        bridge = _bridges.get(instance_id)
    if not bridge:
        raise RuntimeError("Codex interaction connection is not ready")
    return bridge.submit("approval", approval_id=approval_id, decision=decision)
