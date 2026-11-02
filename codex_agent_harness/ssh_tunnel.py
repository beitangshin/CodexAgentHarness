"""Keep an outbound SSH port forward from an agent to the laptop master."""

from __future__ import annotations

import os
import socket
import subprocess

from . import local_tools


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class SshTunnel:
    def __init__(self, target: str, remote_port: int = 8000, ssh_port: int = 22,
                 identity_file: str | None = None, ssh_executable: str | None = None) -> None:
        if not target or target.startswith("-") or any(char.isspace() for char in target):
            raise ValueError("SSH target must be a host alias or user@host")
        if not 1 <= remote_port <= 65535 or not 1 <= ssh_port <= 65535:
            raise ValueError("SSH and master ports must be between 1 and 65535")
        self.target = target
        self.remote_port = remote_port
        self.ssh_port = ssh_port
        self.identity_file = identity_file
        self.ssh_executable = ssh_executable
        self.local_port: int | None = None
        self.process: subprocess.Popen | None = None

    @property
    def base_url(self) -> str:
        if self.local_port is None:
            raise RuntimeError("SSH tunnel has not started")
        return f"http://127.0.0.1:{self.local_port}"

    def ensure_running(self) -> None:
        if self.process is not None and self.process.poll() is None:
            return
        if self.process is not None:
            self.process.wait()
            code = self.process.returncode
            self.process = None
            raise RuntimeError(f"SSH tunnel exited ({code}); check SSH host key, key login and forwarding")
        ssh = self.ssh_executable or local_tools.require("ssh")
        self.local_port = _free_port()
        command = [
            ssh, "-N", "-T", "-p", str(self.ssh_port),
            "-o", "BatchMode=yes",
            "-o", "StrictHostKeyChecking=yes",
            "-o", "ExitOnForwardFailure=yes",
            "-o", "ConnectTimeout=10",
            "-o", "ConnectionAttempts=1",
            "-o", "ServerAliveInterval=15",
            "-o", "ServerAliveCountMax=3",
            "-L", f"127.0.0.1:{self.local_port}:127.0.0.1:{self.remote_port}",
        ]
        if self.identity_file:
            command.extend(["-o", "IdentitiesOnly=yes", "-i", self.identity_file])
        command.append(self.target)
        self.process = subprocess.Popen(
            command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )

    def close(self) -> None:
        if self.process is not None:
            if self.process.poll() is None:
                self.process.terminate()
                try:
                    self.process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait()
            self.process = None
        self.local_port = None
