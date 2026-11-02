import json
import threading
import time
from unittest import TestCase
from unittest.mock import MagicMock

from websockets.sync.server import serve

from codex_agent_harness.interaction import InteractionBridge, augment_snapshot
from codex_agent_harness import interaction


class InteractionBridgeTests(TestCase):
    def bridge(self):
        bridge = object.__new__(InteractionBridge)
        bridge.instance_id = "instance-1"
        bridge.port = 4500
        bridge.lock = threading.Lock()
        bridge.ready = threading.Event()
        bridge.ready.set()
        bridge.pending = {}
        bridge.live_text = ""
        bridge.recent_activity = []
        bridge.thread_id = "thread-1"
        bridge._next_id = 1000
        bridge.stop_event = threading.Event()
        return bridge

    def test_command_approval_is_exposed_and_answered_explicitly(self):
        bridge = self.bridge()
        bridge._handle(MagicMock(), {
            "id": 17, "method": "item/commandExecution/requestApproval",
            "params": {"threadId": "thread-1", "turnId": "turn-1", "itemId": "item-1",
                       "command": "pwd", "cwd": "/home/user/project",
                       "reason": "Read project directory"},
        })
        approval = bridge.snapshot()["pending_approvals"][0]
        self.assertEqual(approval["command"], "pwd")
        self.assertNotIn("request_id", approval)
        ws = MagicMock()
        request = {"kind": "approval", "approval_id": approval["id"], "decision": "accept"}
        bridge._perform(ws, request)
        self.assertEqual(json.loads(ws.send.call_args.args[0]),
                         {"id": 17, "result": {"decision": "accept"}})
        self.assertEqual(bridge.snapshot()["pending_approvals"], [])

    def test_task_uses_persistent_connection_and_keeps_approval_handler(self):
        bridge = self.bridge()
        bridge._call = MagicMock(side_effect=[
            {"thread": {"id": "thread-1", "status": {"type": "idle"}}},
            {"turn": {"id": "turn-1"}},
        ])
        request = {"kind": "task", "prompt": "Check status"}
        bridge._perform(MagicMock(), request)
        self.assertEqual(bridge._call.call_args.args[1], "turn/start")
        self.assertEqual(bridge._call.call_args.args[2]["input"][0]["text"], "Check status")
        self.assertEqual(request["result"], "Task sent to Codex")
        self.assertEqual(bridge.snapshot()["activity"][0]["text"], "Check status")

    def test_streaming_text_and_external_resolution_update_snapshot(self):
        bridge = self.bridge()
        bridge._handle(MagicMock(), {"method": "item/agentMessage/delta",
                                     "params": {"delta": "Working"}})
        self.assertEqual(bridge.snapshot()["live_text"], "Working")
        bridge._handle(MagicMock(), {"method": "turn/completed", "params": {}})
        self.assertEqual(bridge.snapshot()["live_text"], "")
        self.assertEqual(bridge.snapshot()["activity"][-1]["text"], "Working")
        bridge._handle(MagicMock(), {"id": 9, "method": "item/fileChange/requestApproval",
                                     "params": {"threadId": "thread-1"}})
        bridge._handle(MagicMock(), {"method": "serverRequest/resolved",
                                     "params": {"requestId": 9}})
        self.assertEqual(bridge.snapshot()["pending_approvals"], [])

    def test_bridge_reply_is_added_when_history_is_empty(self):
        bridge = self.bridge()
        bridge._handle(MagicMock(), {"method": "item/completed", "params": {
            "item": {"type": "agentMessage", "text": "Done"}}})
        snapshot = {"instances": [{"id": "instance-1", "status": "idle",
                                  "activity": [], "pending_approvals": []}]}
        with interaction._registry_lock:
            previous = interaction._bridges.copy()
            interaction._bridges.clear()
            interaction._bridges["instance-1"] = bridge
        try:
            augment_snapshot(snapshot)
        finally:
            with interaction._registry_lock:
                interaction._bridges.clear()
                interaction._bridges.update(previous)
        self.assertEqual(snapshot["instances"][0]["activity"][0]["text"], "Done")

    def test_master_task_approval_round_trip_over_websocket(self):
        responses = []
        methods = []
        approved = threading.Event()

        def handler(ws):
            while True:
                try:
                    message = json.loads(ws.recv(timeout=5))
                except Exception:
                    return
                method = message.get("method")
                if method:
                    methods.append(method)
                if method == "initialized":
                    continue
                if method == "initialize":
                    result = {}
                elif method == "thread/loaded/list":
                    result = {"data": ["thread-1"]}
                elif method in {"thread/read", "thread/resume"}:
                    result = {"thread": {"id": "thread-1", "status": {"type": "idle"}}}
                elif method == "turn/start":
                    result = {"turn": {"id": "turn-1"}}
                elif method is None and message.get("id") == 77:
                    responses.append(message)
                    approved.set()
                    continue
                else:
                    result = {}
                ws.send(json.dumps({"id": message["id"], "result": result}))
                if method == "turn/start":
                    ws.send(json.dumps({"id": 77,
                                        "method": "item/commandExecution/requestApproval",
                                        "params": {"threadId": "thread-1", "turnId": "turn-1",
                                                   "command": "pwd", "reason": "Read cwd"}}))

        with serve(handler, "127.0.0.1", 0) as server:
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            bridge = InteractionBridge("instance-1", server.socket.getsockname()[1])
            try:
                self.assertTrue(bridge.ready.wait(5), bridge.error)
                self.assertEqual(bridge.submit("task", prompt="Show cwd"), "Task sent to Codex")
                approval = None
                for _ in range(30):
                    pending = bridge.snapshot()["pending_approvals"]
                    if pending:
                        approval = pending[0]
                        break
                    time.sleep(0.1)
                self.assertIsNotNone(approval)
                bridge.submit("approval", approval_id=approval["id"], decision="decline")
                self.assertTrue(approved.wait(2))
                self.assertEqual(responses[0], {"id": 77, "result": {"decision": "decline"}})
                self.assertNotIn("thread/resume", methods)
            finally:
                bridge.stop()
                server.shutdown()
                thread.join(timeout=2)
