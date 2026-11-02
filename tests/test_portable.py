import os
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from codex_agent_harness import connection, local_tools, managed, master, server


class PortableSetupTests(TestCase):
    def test_connection_is_saved_for_next_slave_launch(self):
        with TemporaryDirectory() as directory:
            with patch.object(connection, "CONFIG_PATH", Path(directory) / "agent-connection.json"):
                with self.assertRaisesRegex(ValueError, "both be set"):
                    connection.save({"ssh_target": "master"})
                values = connection.save({"ssh_target": "master", "token": "test-report-token"})
                self.assertEqual(connection.load(), values)
                self.assertEqual(values["ssh_target"], "master")

    def test_local_programs_require_explicit_existing_paths(self):
        with TemporaryDirectory() as directory:
            folder = Path(directory)
            executable = folder / ("codex.exe" if os.name == "nt" else "codex")
            executable.write_bytes(b"test")
            if os.name != "nt":
                executable.chmod(0o700)
            with patch.object(local_tools, "CONFIG_PATH", folder / "local-tools.json"), \
                 patch.object(local_tools, "suggestions", return_value=[]):
                with self.assertRaisesRegex(RuntimeError, "Configure the local codex"):
                    local_tools.require("codex")
                local_tools.save({"codex": str(executable)})
                self.assertEqual(local_tools.require("codex"), str(executable.resolve()))
                with self.assertRaisesRegex(ValueError, "absolute path"):
                    local_tools.save({"ssh": "ssh"})

    def test_terminal_alternative_name_is_preserved(self):
        if os.name == "nt":
            self.skipTest("Linux alternatives use symbolic links")
        with TemporaryDirectory() as directory:
            folder = Path(directory)
            executable = folder / "gnome-terminal.wrapper"
            executable.write_bytes(b"test")
            executable.chmod(0o700)
            alternative = folder / "x-terminal-emulator"
            alternative.symlink_to(executable)
            with patch.object(local_tools, "CONFIG_PATH", folder / "local-tools.json"):
                self.assertEqual(local_tools.save({"terminal": str(alternative)})["terminal"], str(alternative))
                self.assertEqual(managed._terminal_command(local_tools.require("terminal"), ["runner"]),
                                 [str(alternative), "-e", "runner"])

    def test_auto_search_only_fills_missing_or_broken_programs(self):
        with TemporaryDirectory() as directory:
            folder = Path(directory)
            found = folder / "found-codex"
            manual = folder / "manual-codex"
            found.write_bytes(b"test")
            manual.write_bytes(b"test")
            if os.name != "nt":
                found.chmod(0o700)
                manual.chmod(0o700)
            with patch.object(local_tools, "CONFIG_PATH", folder / "local-tools.json"), \
                 patch.object(local_tools, "suggestions", return_value=[str(found)]):
                self.assertEqual(local_tools.auto_configure(("codex",))["codex"], str(found))
                local_tools.save({"codex": str(manual)})
                self.assertEqual(local_tools.auto_configure(("codex",))["codex"], str(manual))
                manual.unlink()
                self.assertEqual(local_tools.auto_configure(("codex",))["codex"], str(found))
                self.assertEqual(local_tools.missing(("codex",)), [])

    def test_windows_prefers_standalone_codex_over_extension_preview(self):
        if os.name != "nt":
            self.skipTest("Windows Codex release layout")
        with TemporaryDirectory() as directory:
            home = Path(directory)
            standalone = home / ".codex" / "packages" / "standalone" / "releases" / "0.166.0" / "bin" / "codex.exe"
            extension = home / ".vscode" / "extensions" / "openai.chatgpt-preview" / "bin" / "windows-x86_64" / "codex.exe"
            for path in (standalone, extension):
                path.parent.mkdir(parents=True)
                path.write_bytes(b"test")
            with patch.object(local_tools.Path, "home", return_value=home), \
                 patch.object(local_tools.shutil, "which", return_value=str(extension)):
                self.assertEqual(local_tools.detect("codex"), str(standalone))

    def test_master_creates_credentials_once_and_reuses_them(self):
        with TemporaryDirectory() as directory:
            folder = Path(directory)
            with patch.object(master, "APP_DIR", folder), \
                 patch.object(master, "CREDENTIALS_PATH", folder / "master-credentials.json"), \
                 patch.dict(os.environ, {}, clear=True):
                master._load_or_create_credentials()
                first = {name: os.environ[name] for name in
                         ("REPORT_TOKEN", "DASHBOARD_USER", "DASHBOARD_PASSWORD")}
                self.assertTrue(all(first.values()))
                for name in first:
                    del os.environ[name]
                master._load_or_create_credentials()
                self.assertEqual(first, {name: os.environ[name] for name in first})

    def test_dashboard_can_configure_only_the_local_machine_programs(self):
        with TemporaryDirectory() as directory:
            folder = Path(directory)
            executable = folder / ("codex.exe" if os.name == "nt" else "codex")
            executable.write_bytes(b"test")
            with patch.object(local_tools, "CONFIG_PATH", folder / "local-tools.json"), \
                 patch.object(local_tools, "suggestions", return_value=[]):
                detected = server.get_local_tools()
                self.assertEqual(detected["configured"]["codex"], "")
                self.assertIn("codex", detected["missing"])
                self.assertEqual(server.set_local_tools(server.LocalToolsRequest(codex=str(executable)))["configured"]["codex"],
                                 str(executable.resolve()))
                self.assertEqual(local_tools.load()["codex"], str(executable.resolve()))
                with self.assertRaisesRegex(Exception, "422"):
                    server.set_local_tools(server.LocalToolsRequest(codex="codex"))

    def test_selected_terminal_receives_the_runner_without_shell_interpolation(self):
        command = ["runner", "run", "--cwd", "a folder"]
        if os.name == "nt":
            self.assertEqual(managed._terminal_command(local_tools.WINDOWS_CONSOLE, command), command)
            actual = managed._terminal_command(r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe", command)
            self.assertEqual(actual[-2], "-EncodedCommand")
            import base64
            self.assertEqual(base64.b64decode(actual[-1]).decode("utf-16le"),
                             "& 'runner' 'run' '--cwd' 'a folder'")
        else:
            self.assertEqual(managed._terminal_command("/usr/bin/x-terminal-emulator", command),
                             ["/usr/bin/x-terminal-emulator", "-e", *command])
