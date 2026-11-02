import json
import threading
from argparse import Namespace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import MagicMock, patch

from codex_agent_harness import agent, master, ssh_tunnel


class TransportTests(TestCase):
    def test_ssh_forward_is_loopback_only_and_checks_host_key(self):
        process = MagicMock()
        process.poll.return_value = None
        with patch.object(ssh_tunnel.local_tools, "require", return_value="/usr/bin/ssh"), \
             patch.object(ssh_tunnel, "_free_port", return_value=18765), \
             patch.object(ssh_tunnel.subprocess, "Popen", return_value=process) as popen:
            tunnel = ssh_tunnel.SshTunnel("codex-harness-laptop", identity_file="/key")
            tunnel.ensure_running()
            command = popen.call_args.args[0]
            self.assertIn("127.0.0.1:18765:127.0.0.1:8000", command)
            self.assertIn("StrictHostKeyChecking=yes", command)
            self.assertIn("BatchMode=yes", command)
            self.assertIn("ExitOnForwardFailure=yes", command)
            self.assertEqual(command[-1], "codex-harness-laptop")
            self.assertEqual(tunnel.base_url, "http://127.0.0.1:18765")
            tunnel.close()
        process.terminate.assert_called_once()

    def test_one_shot_report_uses_the_ssh_local_forward(self):
        tunnel = MagicMock()
        tunnel.base_url = "http://127.0.0.1:18765"
        tunnel.process.poll.return_value = None
        args = Namespace(ssh_target="codex-harness-laptop", ssh_identity=None,
                         ssh_port=22, master_port=8000, local_master=False,
                         machine_id=None, token="test-token", once=True)
        with patch.object(agent, "SshTunnel", return_value=tunnel), \
             patch.object(agent, "_machine_id", return_value="machine-1"), \
             patch.object(agent, "collect_managed", return_value={"cli_process_count": 0, "instances": []}), \
             patch.object(agent, "urlopen") as urlopen:
            agent._report_loop(args)
        self.assertEqual(urlopen.call_args_list[0].args[0], "http://127.0.0.1:18765/healthz")
        request = urlopen.call_args_list[1].args[0]
        self.assertEqual(request.full_url, "http://127.0.0.1:18765/api/report")
        self.assertEqual(request.get_header("Authorization"), "Bearer test-token")
        self.assertEqual(json.loads(request.data)["machine_id"], "machine-1")
        tunnel.close.assert_called_once()

    def test_ssh_tunnel_retries_after_disconnect(self):
        first = MagicMock()
        first.poll.return_value = 255
        first.returncode = 255
        second = MagicMock()
        second.poll.return_value = None
        with patch.object(ssh_tunnel.local_tools, "require", return_value="/usr/bin/ssh"), \
             patch.object(ssh_tunnel, "_free_port", side_effect=[18765, 18766]), \
             patch.object(ssh_tunnel.subprocess, "Popen", side_effect=[first, second]) as popen:
            tunnel = ssh_tunnel.SshTunnel("codex-harness-laptop")
            tunnel.ensure_running()
            with self.assertRaisesRegex(RuntimeError, "SSH tunnel exited"):
                tunnel.ensure_running()
            tunnel.ensure_running()
            self.assertEqual(tunnel.base_url, "http://127.0.0.1:18766")
            self.assertEqual(popen.call_count, 2)
            tunnel.close()

    def test_roaming_home_keeps_separate_machine_ids_per_vdi_host(self):
        with TemporaryDirectory() as directory, patch.object(agent.Path, "home", return_value=Path(directory)):
            first = agent._machine_id(agent._identity_path("VDL000241"))
            second = agent._machine_id(agent._identity_path("VDL000242"))
            self.assertNotEqual(first, second)
            self.assertEqual(first, agent._machine_id(agent._identity_path("VDL000241")))

    def test_master_starts_only_on_loopback(self):
        started = threading.Event()
        captured = {}

        def local_reporter(args, stop):
            captured["args"] = args
            started.set()
            stop.wait(2)

        def serve(*_args, **_kwargs):
            self.assertTrue(started.wait(2))

        with TemporaryDirectory() as directory, \
             patch("sys.argv", ["codex-agent-harness-master"]), \
             patch.dict("os.environ", {"REPORT_TOKEN": "a", "DASHBOARD_USER": "b",
                                        "DASHBOARD_PASSWORD": "c"}), \
             patch.object(master, "_report_loop", side_effect=local_reporter), \
             patch.object(master.local_tools, "auto_configure"), \
             patch.object(master, "_record_process"), \
             patch.object(master, "PROCESS_PATH", Path(directory) / "master-process.json"), \
             patch.object(master.uvicorn, "run", side_effect=serve) as run:
            master.main()
        self.assertEqual(run.call_args.kwargs["host"], "127.0.0.1")
        self.assertEqual(run.call_args.kwargs["port"], 8000)
        self.assertTrue(captured["args"].local_master)
        self.assertEqual(captured["args"].token, "a")

    def test_master_can_disable_embedded_slave_for_separate_local_agent(self):
        with TemporaryDirectory() as directory, \
             patch("sys.argv", ["codex-agent-harness-master", "--no-local-slave"]), \
             patch.dict("os.environ", {"REPORT_TOKEN": "a", "DASHBOARD_USER": "b",
                                        "DASHBOARD_PASSWORD": "c"}), \
             patch.object(master, "_report_loop") as reporter, \
             patch.object(master.local_tools, "auto_configure"), \
             patch.object(master, "_record_process"), \
             patch.object(master, "PROCESS_PATH", Path(directory) / "master-process.json"), \
             patch.object(master.uvicorn, "run"):
            master.main()
        reporter.assert_not_called()
