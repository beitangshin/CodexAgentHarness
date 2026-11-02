import os
import sys
from unittest import TestCase
from unittest.mock import patch

from codex_agent_harness import agent


class AgentCliTests(TestCase):
    def test_launcher_only_does_not_start_another_reporter(self):
        with patch.dict(os.environ, {
            "CODEX_AGENT_HARNESS_SSH_TARGET": "codex-harness-laptop",
            "CODEX_AGENT_HARNESS_REPORT_TOKEN": "test-token",
        }), patch.object(sys, "argv", ["codex-agent-harness", "--launcher-only"]), \
             patch("codex_agent_harness.gui.run_gui") as gui, \
             patch.object(agent.threading, "Thread") as reporter:
            agent.main()
        gui.assert_called_once_with(reporting=False, external_reporting=True)
        reporter.assert_not_called()
