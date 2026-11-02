import json
import os
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import MagicMock, patch

from codex_agent_harness import managed
from codex_agent_harness.server import Report


def configured_tool(kind):
    if kind == "codex":
        return "/bin/codex"
    return "windows-console" if os.name == "nt" else "/usr/bin/x-terminal-emulator"


class ManagedTests(TestCase):
    def test_runner_imports_from_project_directory(self):
        with TemporaryDirectory() as other_directory:
            result = subprocess.run(
                [sys.executable, "-m", "codex_agent_harness.managed", "--help"],
                cwd=other_directory, env=managed._runner_environment(),
                capture_output=True, text=True, timeout=10,
            )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_runner_does_not_inherit_master_credentials(self):
        values = {"REPORT_TOKEN": "report-secret", "DASHBOARD_USER": "admin",
                  "DASHBOARD_PASSWORD": "dashboard-secret",
                  "CODEX_AGENT_HARNESS_REPORT_TOKEN": "agent-secret"}
        with patch.dict(os.environ, values):
            environment = managed._runner_environment()
        for name in values:
            self.assertNotIn(name, environment)

    def test_external_windows_cli_is_visible_but_not_managed(self):
        if os.name != "nt":
            self.skipTest("Windows process discovery")
        standalone = MagicMock()
        standalone.info = {"pid": 4242, "name": "codex.exe", "cmdline": ["codex.exe"],
                           "create_time": 1_750_000_000.0}
        standalone.cmdline.return_value = ["codex.exe"]
        standalone.create_time.return_value = 1_750_000_000.0
        standalone.cwd.return_value = r"C:\work\project"
        server = MagicMock()
        server.info = {"pid": 4343, "name": "codex.exe", "cmdline": ["codex.exe", "app-server"],
                       "create_time": 1_750_000_000.0}
        server.cmdline.return_value = ["codex.exe", "app-server"]
        with patch.object(managed, "_external_scan_at", 0.0), \
             patch.object(managed, "_external_cache", []), \
             patch.object(managed.psutil, "process_iter", return_value=[standalone, server]):
            discovered = managed._external_cli_instances(set())
            excluded = managed._external_cli_instances({4242})
        self.assertEqual(len(discovered), 1)
        self.assertEqual(discovered[0]["pid"], 4242)
        self.assertFalse(discovered[0]["managed"])
        self.assertEqual(discovered[0]["status"], "unknown")
        self.assertEqual(excluded, [])

    def test_model_and_effort_reach_cli_and_record(self):
        with TemporaryDirectory() as directory:
            folder = Path(directory)
            with patch.object(managed, "STATE_DIR", folder / "instances"), \
                 patch.object(managed.local_tools, "require", side_effect=configured_tool), \
                 patch.object(managed.subprocess, "Popen") as popen:
                instance_id = managed.launch_terminal(folder, model="gpt-6-sol", effort="high")
            record = json.loads((folder / "instances" / f"{instance_id}.json").read_text(encoding="utf-8"))
            self.assertEqual((record["model"], record["reasoning_effort"]), ("gpt-6-sol", "high"))
            self.assertEqual(popen.call_args.args[0][-4:], ["--model", "gpt-6-sol", "--effort", "high"])
            self.assertEqual(managed._model_flags("gpt-6-sol", "high"),
                             ["--model", "gpt-6-sol", "--config", "model_reasoning_effort=high"])

    def test_directory_browser_lists_directories_only(self):
        with TemporaryDirectory() as directory:
            folder = Path(directory)
            (folder / "project-b").mkdir()
            (folder / "project-a").mkdir()
            (folder / "secret.txt").write_text("never return this content", encoding="utf-8")
            listing = managed.browse_directories(str(folder))
            self.assertEqual(listing["directories"], ["project-a", "project-b"])
            self.assertEqual(listing["path"], str(folder.resolve()))

    def test_recent_turn_metadata_reports_actual_model_and_effort(self):
        with TemporaryDirectory() as directory:
            folder = Path(directory)
            thread_id = str(uuid.uuid4())
            rollout = folder / f"rollout-{thread_id}.jsonl"
            rollout.write_text("\n".join(json.dumps({"type": "turn_context", "payload": {
                "model": model, "effort": effort}}) for model, effort in
                [("gpt-6-luna", "low"), ("gpt-6-sol", "high")]) + "\n", encoding="utf-8")
            with patch.object(managed, "SESSION_DIR", folder):
                self.assertEqual(managed._latest_turn_model(thread_id), ("gpt-6-sol", "high"))

    def test_launch_button_registers_and_spawns_a_terminal(self):
        with TemporaryDirectory() as directory:
            folder = Path(directory)
            with patch.object(managed, "STATE_DIR", folder / "instances"), \
                 patch.object(managed.local_tools, "require", side_effect=configured_tool), \
                 patch.object(managed.subprocess, "Popen") as popen:
                instance_id = managed.launch_terminal(folder)
            record = json.loads((folder / "instances" / f"{instance_id}.json").read_text(encoding="utf-8"))
            self.assertEqual(record["state"], "starting")
            self.assertEqual(record["cwd"], str(folder.resolve()))
            self.assertTrue(popen.called)
            if os.name == "nt":
                self.assertEqual(popen.call_args.kwargs["creationflags"], managed.subprocess.CREATE_NEW_CONSOLE)

    def test_frozen_launcher_reuses_the_binary_for_instance_runner(self):
        with TemporaryDirectory() as directory:
            folder = Path(directory)
            with patch.object(managed, "STATE_DIR", folder / "instances"), \
                 patch.object(managed.local_tools, "require", side_effect=configured_tool), \
                 patch.object(managed.sys, "frozen", True, create=True), \
                 patch.object(managed.subprocess, "Popen") as popen:
                managed.launch_terminal(folder)
            command = popen.call_args.args[0]
            if os.name != "nt":
                command = command[2:]
            self.assertEqual(command[:2], [sys.executable, "run"])

    def test_launch_mode_is_saved_and_forwarded_to_runner(self):
        with TemporaryDirectory() as directory:
            folder = Path(directory)
            with patch.object(managed, "STATE_DIR", folder / "instances"), \
                 patch.object(managed.local_tools, "require", side_effect=configured_tool), \
                 patch.object(managed.subprocess, "Popen") as popen:
                instance_id = managed.launch_terminal(folder, mode="bypass")
            record = json.loads((folder / "instances" / f"{instance_id}.json").read_text(encoding="utf-8"))
            self.assertEqual(record["launch_mode"], "bypass")
            self.assertEqual(popen.call_args.args[0][-2:], ["--mode", "bypass"])

    def test_modes_produce_distinct_codex_flags(self):
        self.assertEqual(managed._mode_flags("default"), [])
        self.assertEqual(managed._mode_flags("full_access"),
                         ["--sandbox", "danger-full-access", "--ask-for-approval", "on-request"])
        self.assertEqual(managed._mode_flags("bypass"),
                         ["--dangerously-bypass-approvals-and-sandbox"])
        with self.assertRaises(ValueError):
            managed._mode_flags("not-a-mode")

    def test_full_access_flags_reach_the_codex_tui(self):
        with TemporaryDirectory() as directory:
            app_server = MagicMock(pid=301)
            cli = MagicMock(pid=302)
            cli.wait.return_value = 0
            with patch.object(managed, "STATE_DIR", Path(directory) / "instances"), \
                 patch.object(managed, "_free_port", return_value=4500), \
                 patch.object(managed, "_ready"), \
                 patch.object(managed.psutil, "Process") as process, \
                 patch.object(managed.subprocess, "Popen", side_effect=[app_server, cli]) as popen:
                process.return_value.create_time.return_value = 1.0
                code = managed.run_instance("test-instance", Path(directory), "/bin/codex", "full_access")
            self.assertEqual(code, 0)
            self.assertEqual(popen.call_args_list[1].args[0][1:3],
                             ["--remote", "ws://127.0.0.1:4500"])
            self.assertEqual(popen.call_args_list[1].args[0][-4:],
                             ["--sandbox", "danger-full-access", "--ask-for-approval", "on-request"])
            record = json.loads((Path(directory) / "instances" / "test-instance.json").read_text(encoding="utf-8"))
            self.assertEqual(record["cli_pid"], 302)

    def test_explicit_project_trust_is_saved_and_read_back_from_codex(self):
        with TemporaryDirectory() as directory:
            folder = Path(directory)
            saved = {"config": {"projects": {str(folder): {"trust_level": "trusted"}}}}
            with patch.object(managed, "_free_port", return_value=4500), \
                 patch.object(managed, "_ready"), \
                 patch.object(managed.subprocess, "Popen") as popen, \
                 patch.object(managed, "connect"), \
                 patch.object(managed, "_rpc", side_effect=[{}, {"status": "ok"}, saved]) as rpc:
                managed._persist_project_trust(folder, "/bin/codex")
            self.assertEqual(popen.call_args.args[0][1], "app-server")
            self.assertEqual(rpc.call_args_list[1].args[1], "config/batchWrite")
            edit = rpc.call_args_list[1].args[3]["edits"][0]
            self.assertEqual(edit, {
                "keyPath": f'projects.{json.dumps(str(folder))}.trust_level',
                "value": "trusted", "mergeStrategy": "replace",
            })
            self.assertEqual(rpc.call_args_list[2].args[1], "config/read")

    def test_project_trust_write_failure_keeps_current_instance_running(self):
        with TemporaryDirectory() as directory:
            folder = Path(directory)
            instance_id = str(uuid.uuid4())
            record = {"id": instance_id, "cwd": str(folder), "launch_mode": "default"}
            with patch.object(managed, "_read_record", return_value=record), \
                 patch.object(managed, "_codex_executable", return_value="/bin/codex"), \
                 patch.object(managed, "_persist_project_trust", side_effect=RuntimeError("write failed")), \
                 patch.object(managed, "stop_instance") as stop:
                with self.assertRaisesRegex(RuntimeError, "write failed"):
                    managed.restart_instance(instance_id, trust_project=True)
            stop.assert_not_called()

    def test_restart_preserves_project_trust(self):
        instance_id = str(uuid.uuid4())
        record = {"id": instance_id, "cwd": "/tmp/demo", "launch_mode": "default",
                  "trust_project": True}
        with patch.object(managed, "_read_record", return_value=record), \
             patch.object(managed, "launch_terminal", return_value=instance_id) as launch:
            managed.restart_instance(instance_id)
        launch.assert_called_once_with(Path("/tmp/demo"), "default", instance_id, None, None, True)

    def test_restart_reuses_instance_id_and_replaces_old_pid(self):
        with TemporaryDirectory() as directory:
            folder = Path(directory)
            instance_id = str(uuid.uuid4())
            records = folder / "instances"
            records.mkdir()
            (records / f"{instance_id}.json").write_text(json.dumps({
                "id": instance_id, "cwd": str(folder), "state": "exited",
                "started_at": datetime.now(timezone.utc).isoformat(),
                "ended_at": datetime.now(timezone.utc).isoformat(),
                "cli_pid": 123, "cli_created": 1.0, "launch_mode": "bypass",
            }), encoding="utf-8")
            with patch.object(managed, "STATE_DIR", records), \
                 patch.object(managed, "_alive", return_value=False), \
                 patch.object(managed.local_tools, "require", side_effect=configured_tool), \
                 patch.object(managed.subprocess, "Popen") as popen:
                restarted = managed.restart_instance(instance_id)
            record = json.loads((records / f"{instance_id}.json").read_text(encoding="utf-8"))
            self.assertEqual(restarted, instance_id)
            self.assertEqual(record["state"], "starting")
            self.assertNotIn("cli_pid", record)
            self.assertEqual(record["launch_mode"], "bypass")
            self.assertEqual(popen.call_args.args[0][-2:], ["--mode", "bypass"])

    def test_restart_live_instance_applies_new_permission_mode(self):
        instance_id = str(uuid.uuid4())
        record = {"id": instance_id, "cwd": "/tmp/demo", "launch_mode": "default",
                  "cli_pid": 123, "cli_created": 1.0}
        stopped = False
        def alive(pid, _created):
            return bool(pid) and not stopped
        def stop(_instance_id):
            nonlocal stopped
            stopped = True
        with patch.object(managed, "_read_record", return_value=record), \
             patch.object(managed, "_alive", side_effect=alive), \
             patch.object(managed, "stop_instance", side_effect=stop) as stop_mock, \
             patch.object(managed, "launch_terminal", return_value=instance_id) as launch:
            managed.restart_instance(instance_id, "full_access")
        stop_mock.assert_called_once_with(instance_id)
        launch.assert_called_once_with(Path("/tmp/demo"), "full_access", instance_id, None, None, False)

    def test_restart_exited_cli_kills_tracked_auxiliary_and_reuses_id(self):
        instance_id = str(uuid.uuid4())
        record = {"id": instance_id, "cwd": "/tmp/demo", "state": "exited",
                  "cli_pid": 123, "cli_created": 1.0,
                  "runner_pid": 124, "runner_created": 2.0,
                  "launch_mode": "default"}
        killed = False
        process = MagicMock()
        process.is_running.return_value = True
        process.create_time.return_value = 2.0
        def kill():
            nonlocal killed
            killed = True
        process.kill.side_effect = kill
        with patch.object(managed, "_read_record", return_value=record), \
             patch.object(managed, "_alive", side_effect=lambda pid, _: pid == 124 and not killed), \
             patch.object(managed, "stop_instance") as stop, \
             patch.object(managed.psutil, "Process", return_value=process), \
             patch.object(managed.time, "sleep"), \
             patch.object(managed, "launch_terminal", return_value=instance_id) as launch:
            actual = managed.restart_instance(instance_id, "bypass")
        self.assertEqual(actual, instance_id)
        stop.assert_called_once_with(instance_id)
        process.kill.assert_called_once()
        launch.assert_called_once_with(Path("/tmp/demo"), "bypass", instance_id, None, None, False)

    def test_restart_refuses_second_cli_if_old_cli_stays_alive(self):
        instance_id = str(uuid.uuid4())
        record = {"id": instance_id, "cwd": "/tmp/demo", "state": "running",
                  "cli_pid": 123, "cli_created": 1.0}
        with patch.object(managed, "_read_record", return_value=record), \
             patch.object(managed, "_alive", side_effect=lambda pid, _: pid == 123), \
             patch.object(managed, "stop_instance"), \
             patch.object(managed.time, "sleep"), \
             patch.object(managed, "launch_terminal") as launch:
            with self.assertRaisesRegex(RuntimeError, "cli PID 123"):
                managed.restart_instance(instance_id)
        launch.assert_not_called()

    def test_delete_exited_record_cleans_tracked_orphan(self):
        with TemporaryDirectory() as directory:
            instance_id = str(uuid.uuid4())
            path = Path(directory, f"{instance_id}.json")
            path.write_text(json.dumps({"id": instance_id, "state": "exited",
                                        "runner_pid": 124, "runner_created": 2.0}), encoding="utf-8")
            killed = False
            process = MagicMock()
            process.is_running.return_value = True
            process.create_time.return_value = 2.0
            def kill():
                nonlocal killed
                killed = True
            process.kill.side_effect = kill
            with patch.object(managed, "STATE_DIR", Path(directory)), \
                 patch.object(managed, "_alive", side_effect=lambda pid, _: pid == 124 and not killed), \
                 patch.object(managed, "stop_instance"), \
                 patch.object(managed.psutil, "Process", return_value=process), \
                 patch.object(managed.time, "sleep"):
                managed.delete_instance(instance_id)
            self.assertFalse(path.exists())
            process.kill.assert_called_once()

    def test_delete_history_refuses_a_live_instance(self):
        with TemporaryDirectory() as directory:
            instance_id = str(uuid.uuid4())
            path = Path(directory, f"{instance_id}.json")
            path.write_text(json.dumps({"id": instance_id, "cli_pid": 123, "cli_created": 1.0}),
                            encoding="utf-8")
            with patch.object(managed, "STATE_DIR", Path(directory)), \
                 patch.object(managed, "_alive", return_value=True):
                with self.assertRaises(RuntimeError):
                    managed.delete_instance(instance_id)
            self.assertTrue(path.exists())
            with patch.object(managed, "STATE_DIR", Path(directory)), \
                 patch.object(managed, "_alive", return_value=False):
                managed.delete_instance(instance_id)
            self.assertFalse(path.exists())

    def test_stop_only_terminates_the_tracked_pid(self):
        with TemporaryDirectory() as directory:
            instance_id = str(uuid.uuid4())
            path = Path(directory, f"{instance_id}.json")
            path.write_text(json.dumps({"id": instance_id, "state": "running",
                                        "cli_pid": 123, "cli_created": 1.0}), encoding="utf-8")
            process = MagicMock()
            process.is_running.return_value = True
            process.create_time.return_value = 2.0
            with patch.object(managed, "STATE_DIR", Path(directory)), \
                 patch.object(managed.psutil, "Process", return_value=process):
                managed.stop_instance(instance_id)
            process.terminate.assert_not_called()
            self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["state"], "exited")

    def test_one_registered_instance_uses_its_own_app_server_status(self):
        with TemporaryDirectory() as directory:
            record = {
                "id": "instance-1", "cwd": directory, "state": "running",
                "started_at": datetime.now(timezone.utc).isoformat(),
                "runner_pid": 101, "runner_created": 1.0,
                "app_server_pid": 102, "app_server_created": 2.0,
                "cli_pid": 103, "cli_created": 3.0, "port": 4500,
            }
            Path(directory, "instance-1.json").write_text(json.dumps(record), encoding="utf-8")
            with patch.object(managed, "STATE_DIR", Path(directory)), \
                 patch.object(managed, "_alive", side_effect=lambda pid, _: pid in {101, 102, 103}), \
                 patch.object(managed, "_external_cli_instances", return_value=[]), \
                 patch.object(managed, "_thread_state", return_value=("working", "thread-1", None, [
                     {"kind": "Codex", "text": "Working", "status": ""},
                 ])):
                snapshot = managed.collect_managed()
            self.assertEqual(snapshot["cli_process_count"], 1)
            self.assertEqual(snapshot["instances"][0]["id"], "instance-1")
            self.assertEqual(snapshot["instances"][0]["thread_id"], "thread-1")
            self.assertEqual(snapshot["instances"][0]["status"], "working")
            self.assertEqual(snapshot["instances"][0]["activity"][0]["text"], "Working")

    def test_runtime_waiting_flag_maps_to_attention(self):
        ws = MagicMock()
        ws.__enter__.return_value = ws
        current = {"id": "thread-1", "updatedAt": 1000,
                   "status": {"type": "active", "activeFlags": ["waitingOnApproval"]}}
        with patch.object(managed, "connect", return_value=ws), \
             patch.object(managed, "_rpc", side_effect=[{}, {"data": ["thread-1"]},
                                                     {"thread": current}, {"data": []},
                                                     {"data": []}, {"thread": {"turns": []}}]):
            status, thread_id, _, activity = managed._thread_state(4500)
        self.assertEqual((status, thread_id), ("attention", "thread-1"))
        self.assertEqual(activity, [])

    def test_recent_activity_shows_messages_and_command_output_in_order(self):
        newest_first = [
            {"item": {"type": "commandExecution", "command": "pytest", "aggregatedOutput": "2 passed", "status": "completed"}},
            {"item": {"type": "agentMessage", "text": "Running tests"}},
            {"item": {"type": "userMessage", "content": [{"type": "text", "text": "Check tests"}]}},
        ]
        with patch.object(managed, "_rpc", return_value={"data": newest_first}) as rpc:
            activity = managed._recent_activity(MagicMock(), "thread-1")
        self.assertEqual([entry["kind"] for entry in activity], ["用户", "Codex", "命令"])
        self.assertIn("2 passed", activity[-1]["text"])
        self.assertEqual(rpc.call_args.args[1], "thread/items/list")

    def test_recent_activity_falls_back_to_turns_when_items_are_unsupported(self):
        turn = {"items": [{"type": "agentMessage", "text": "In progress"}]}
        with patch.object(managed, "_rpc", side_effect=[RuntimeError("unsupported"),
                                                      {"data": [turn]}]):
            activity = managed._recent_activity(MagicMock(), "thread-1")
        self.assertEqual(activity[0]["text"], "In progress")

    def test_recent_activity_falls_back_when_items_list_is_empty(self):
        turn = {"items": [{"type": "agentMessage", "text": "Recent answer"}]}
        with patch.object(managed, "_rpc", side_effect=[{"data": []}, {"data": [turn]}]):
            activity = managed._recent_activity(MagicMock(), "thread-1")
        self.assertEqual(activity[0]["text"], "Recent answer")

    def test_send_task_starts_turn_in_idle_thread(self):
        instance_id = str(uuid.uuid4())
        record = {"id": instance_id, "port": 4500, "cli_pid": 1, "cli_created": 1,
                  "app_server_pid": 2, "app_server_created": 2}
        ws = MagicMock()
        ws.__enter__.return_value = ws
        with patch.object(managed, "_read_record", return_value=record), \
             patch.object(managed, "_alive", return_value=True), \
             patch.object(managed, "connect", return_value=ws), \
             patch.object(managed, "_rpc", side_effect=[{}, {"data": ["thread-1"]},
                                                     {"thread": {"id": "thread-1", "status": {"type": "idle"}}},
                                                     {"turn": {"id": "turn-1"}}]) as rpc:
            message = managed.send_task(instance_id, "  Check status  ")
        self.assertIn("sent", message)
        self.assertEqual(rpc.call_args.args[1], "turn/start")
        self.assertEqual(rpc.call_args.args[3]["input"][0]["text"], "Check status")

    def test_send_task_steers_active_turn(self):
        instance_id = str(uuid.uuid4())
        record = {"port": 4500, "cli_pid": 1, "cli_created": 1,
                  "app_server_pid": 2, "app_server_created": 2}
        ws = MagicMock()
        ws.__enter__.return_value = ws
        with patch.object(managed, "_read_record", return_value=record), \
             patch.object(managed, "_alive", return_value=True), \
             patch.object(managed, "connect", return_value=ws), \
             patch.object(managed, "_rpc", side_effect=[{}, {"data": ["thread-1"]},
                                                     {"thread": {"id": "thread-1", "status": {"type": "active"}}},
                                                     {"data": [{"id": "turn-1"}]},
                                                     {"turnId": "turn-1"}]) as rpc:
            managed.send_task(instance_id, "Focus on tests")
        self.assertEqual(rpc.call_args.args[1], "turn/steer")
        self.assertEqual(rpc.call_args.args[3]["expectedTurnId"], "turn-1")

    def test_recent_activity_falls_back_to_thread_read_on_older_servers(self):
        turn = {"items": [{"type": "agentMessage", "text": "Older server"}]}
        with patch.object(managed, "_rpc", side_effect=[RuntimeError("unsupported"),
                                                      RuntimeError("unsupported"),
                                                      {"thread": {"turns": [turn]}}]):
            activity = managed._recent_activity(MagicMock(), "thread-1")
        self.assertEqual(activity[0]["text"], "Older server")

    def test_closed_terminal_is_recorded_as_exited(self):
        with TemporaryDirectory() as directory:
            record = {
                "id": "instance-2", "cwd": directory, "state": "running",
                "started_at": datetime.now(timezone.utc).isoformat(),
                "runner_pid": 201, "runner_created": 1.0,
                "app_server_pid": 202, "app_server_created": 2.0,
                "cli_pid": 203, "cli_created": 3.0, "port": 4501,
            }
            path = Path(directory, "instance-2.json")
            path.write_text(json.dumps(record), encoding="utf-8")
            with patch.object(managed, "STATE_DIR", Path(directory)), \
                 patch.object(managed, "_external_cli_instances", return_value=[]), \
                 patch.object(managed, "_alive", return_value=False):
                snapshot = managed.collect_managed()
            self.assertEqual(snapshot["cli_process_count"], 0)
            self.assertEqual(snapshot["instances"][0]["status"], "exited")
            self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["state"], "exited")

    def test_report_schema_accepts_managed_instance(self):
        report = Report.model_validate({
            "machine_id": "machine", "hostname": "host", "platform": "windows",
            "cli_process_count": 1, "instances": [{
                "id": "instance-1", "thread_id": "thread-1", "project": "project",
                "status": "working", "confidence": "confirmed", "pid": 123,
                "last_activity": datetime.now(timezone.utc).isoformat(),
                "activity": [{"kind": "Codex", "text": "Working", "status": ""}],
            }],
        })
        self.assertEqual(report.instances[0].thread_id, "thread-1")
        self.assertEqual(report.instances[0].activity[0].text, "Working")

    def test_report_schema_accepts_failed_launch_without_pid(self):
        report = Report.model_validate({
            "machine_id": "machine", "hostname": "host", "platform": "windows",
            "cli_process_count": 0, "instances": [{
                "id": "instance-1", "project": "project", "status": "error",
                "confidence": "confirmed", "pid": None,
                "error": "Codex app-server exited early",
                "last_activity": datetime.now(timezone.utc).isoformat(),
            }],
        })
        self.assertIsNone(report.instances[0].pid)
        self.assertIn("app-server", report.instances[0].error)
