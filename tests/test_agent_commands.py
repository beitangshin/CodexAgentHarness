import json
from io import BytesIO
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

from codex_agent_harness import agent


class AgentCommandTests(TestCase):
    def test_start_command_uses_the_requested_project_and_mode(self):
        command = {"action": "start", "instance_id": "instance-1",
                   "cwd": "/home/user/project", "mode": "full_access"}
        with patch.object(agent, "launch_terminal") as launch:
            agent._execute_command(command)
        launch.assert_called_once_with(Path("/home/user/project"), "full_access", "instance-1", None, None, False)

    def test_task_command_sends_prompt_to_selected_instance(self):
        command = {"action": "task", "instance_id": "instance-1", "prompt": "Check status"}
        with patch.object(agent, "send_task", return_value="Task sent") as dispatch:
            self.assertEqual(agent._execute_command(command), "Task sent")
        dispatch.assert_called_once_with("instance-1", "Check status")

    def test_restart_applies_selected_mode_and_approval_is_forwarded(self):
        with patch.object(agent, "restart_instance") as restart:
            agent._execute_command({"action": "restart", "instance_id": "instance-1",
                                    "mode": "full_access"})
        restart.assert_called_once_with("instance-1", "full_access", None, None, None)

    def test_trust_restart_reaches_slave(self):
        with patch.object(agent, "restart_instance") as restart:
            agent._execute_command({"action": "trust_project", "instance_id": "instance-1"})
        restart.assert_called_once_with("instance-1", None, None, None, True)
        with patch.object(agent, "answer_approval", return_value="sent") as answer:
            result = agent._execute_command({"action": "approval", "instance_id": "instance-1",
                                             "approval_id": "approval-1", "decision": "decline"})
        self.assertEqual(result, "sent")
        answer.assert_called_once_with("instance-1", "approval-1", "decline")

    def test_pending_command_is_acknowledged_with_the_machine_id(self):
        pending = {"commands": [{"id": "command-1", "action": "stop", "instance_id": "instance-1"}]}
        with patch.object(agent, "urlopen", side_effect=[BytesIO(json.dumps(pending).encode()),
                                                          BytesIO(b"")]) as open_url, \
             patch.object(agent, "_execute_command", return_value="stopped"):
            found = agent._poll_commands("http://127.0.0.1:8000", "token", "vdi-test")
        self.assertTrue(found)
        result = open_url.call_args_list[1].args[0]
        self.assertEqual(result.get_method(), "POST")
        self.assertEqual(json.loads(result.data), {
            "machine_id": "vdi-test", "success": True, "message": "stopped", "data": None,
        })
