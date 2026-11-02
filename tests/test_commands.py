import os
import time
import uuid
from datetime import datetime, timezone
from unittest import TestCase
from unittest.mock import patch

from fastapi import HTTPException
from fastapi.security import HTTPBasicCredentials

from codex_agent_harness import server


class CommandTests(TestCase):
    def setUp(self):
        self.environment = patch.dict(os.environ, {
            "REPORT_TOKEN": "report-test-token",
            "DASHBOARD_USER": "admin",
            "DASHBOARD_PASSWORD": "dashboard-test-password",
        })
        self.environment.start()
        with server._lock:
            server._machines.clear()
            server._commands.clear()
        self.instance_id = str(uuid.uuid4())
        report = server.Report.model_validate({
            "machine_id": "vdi-test", "hostname": "VDI-TEST", "platform": "linux",
            "cli_process_count": 1,
            "instances": [{"id": self.instance_id, "project": "demo", "cwd": "/home/user/demo",
                           "status": "idle", "confidence": "confirmed", "pid": 123,
                           "last_activity": datetime.now(timezone.utc).isoformat()}],
        })
        server.report_status(report, "Bearer report-test-token")

    def tearDown(self):
        with server._lock:
            server._machines.clear()
            server._commands.clear()
        self.environment.stop()

    def test_master_queues_agent_claims_and_reports_result(self):
        server._dashboard_auth(HTTPBasicCredentials(username="admin", password="dashboard-test-password"))
        command = server.create_command(server.CommandRequest(
            machine_id="vdi-test", action="restart", instance_id=self.instance_id))
        command_id = command["id"]
        with self.assertRaises(HTTPException):
            server.pending_commands("vdi-test", "Bearer wrong-token")
        pending = server.pending_commands("vdi-test", "Bearer report-test-token")
        self.assertEqual([item["id"] for item in pending["commands"]], [command_id])
        self.assertEqual(server.pending_commands("vdi-test", "Bearer report-test-token")["commands"], [])
        server.finish_command(command_id, server.CommandResult(
            machine_id="vdi-test", success=True, message="restarted"), "Bearer report-test-token")
        status = server.get_status()
        self.assertEqual(status["commands"][0]["status"], "succeeded")
        self.assertEqual(status["commands"][0]["message"], "restarted")

    def test_directory_lookup_returns_structured_result(self):
        command = server.create_command(server.CommandRequest(
            machine_id="vdi-test", action="browse", cwd="/home/user"))
        pending = server.pending_commands("vdi-test", "Bearer report-test-token")["commands"]
        self.assertEqual(pending[0]["cwd"], "/home/user")
        data = {"path": "/home/user", "parent": "/home", "directories": ["projects"], "truncated": False}
        server.finish_command(command["id"], server.CommandResult(
            machine_id="vdi-test", success=True, data=data), "Bearer report-test-token")
        self.assertEqual(server.get_status()["commands"][0]["data"], data)

    def test_external_cli_cannot_receive_managed_actions(self):
        external_id = "external-4242-1750000000000"
        with server._lock:
            server._machines["vdi-test"]["instances"].append({
                "id": external_id, "managed": False, "status": "unknown",
                "pending_approvals": [],
            })
        for action in ("stop", "restart", "delete", "task"):
            with self.assertRaises(HTTPException) as error:
                server.create_command(server.CommandRequest(
                    machine_id="vdi-test", action=action, instance_id=external_id,
                    prompt="test" if action == "task" else None))
            self.assertEqual(error.exception.status_code, 409)

    def test_master_start_has_fixed_instance_id_and_rejects_offline_machine(self):
        command = server.create_command(server.CommandRequest(
            machine_id="vdi-test", action="start", cwd="/home/user/project", mode="full_access"))
        self.assertEqual(command["mode"], "full_access")
        self.assertEqual(str(uuid.UUID(command["instance_id"])), command["instance_id"])
        with server._lock:
            server._machines["vdi-test"]["received_monotonic"] = time.monotonic() - 46
        with self.assertRaises(HTTPException) as error:
            server.create_command(server.CommandRequest(
                machine_id="vdi-test", action="start", cwd="/home/user/project"))
        self.assertEqual(error.exception.status_code, 409)

    def test_master_task_reaches_agent_without_exposing_prompt_in_status(self):
        command = server.create_command(server.CommandRequest(
            machine_id="vdi-test", action="task", instance_id=self.instance_id,
            prompt="Check the current work"))
        self.assertNotIn("prompt", command)
        self.assertNotIn("prompt", server.get_status()["commands"][0])
        pending = server.pending_commands("vdi-test", "Bearer report-test-token")
        self.assertEqual(pending["commands"][0]["prompt"], "Check the current work")

    def test_permission_restart_and_approval_are_scoped_to_instance(self):
        restart = server.create_command(server.CommandRequest(
            machine_id="vdi-test", action="restart", instance_id=self.instance_id,
            mode="bypass"))
        self.assertEqual(restart["mode"], "bypass")
        with self.assertRaises(HTTPException) as error:
            server.create_command(server.CommandRequest(
                machine_id="vdi-test", action="approval", instance_id=self.instance_id,
                approval_id="approval-1", decision="accept"))
        self.assertEqual(error.exception.status_code, 409)
        with server._lock:
            server._machines["vdi-test"]["instances"][0]["pending_approvals"] = [{
                "id": "approval-1", "kind": "command", "thread_id": "thread-1",
                "turn_id": "turn-1", "item_id": "item-1", "reason": "", "command": "pwd",
                "cwd": "/home/user/demo", "available_decisions": [],
            }]
        approval = server.create_command(server.CommandRequest(
            machine_id="vdi-test", action="approval", instance_id=self.instance_id,
            approval_id="approval-1", decision="accept"))
        self.assertEqual(approval["decision"], "accept")

    def test_project_trust_is_only_queued_for_explicit_restart(self):
        trusted = server.create_command(server.CommandRequest(
            machine_id="vdi-test", action="trust_project", instance_id=self.instance_id))
        self.assertEqual(trusted["action"], "trust_project")
        pending = server.pending_commands("vdi-test", "Bearer report-test-token")["commands"]
        self.assertEqual(pending[0]["action"], "trust_project")
        self.assertNotIn("trust_project", pending[0])
