"""
ipc_adapter.py - IPC Client Adapter for pico-fan Daemon
=========================================================
Provides an IPC client interface to communicate with the pico-fan daemon
via UNIX domain socket, allowing commands such as querying status, setting
manual duty cycle, and resuming automatic control.
"""

from __future__ import annotations

import json
import socket
from typing import Any


SOCK_PATH = "/run/pico-fan.sock"
DEFAULT_TIMEOUT = 3.0


class IpcAdapter:
    """Sends commands to the daemon and parses socket responses."""

    def __init__(self, socket_path: str = SOCK_PATH, timeout: float = DEFAULT_TIMEOUT) -> None:
        self.socket_path = socket_path
        self.timeout = timeout

    def send_command(self, command: str = "") -> str | None:
        """Sends an IPC command and returns the line-based response."""
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
                connection.settimeout(self.timeout)
                connection.connect(self.socket_path)
                if command:
                    connection.sendall((command + "\n").encode("utf-8"))

                data = b""
                while b"\n" not in data:
                    chunk = connection.recv(1024)
                    if not chunk:
                        break
                    data += chunk

                return data.decode("utf-8", errors="replace").strip() if data else None
        except (OSError, socket.timeout):
            return None

    def get_status(self) -> dict[str, Any] | None:
        """Queries the current status from the running daemon."""
        response = self.send_command()
        if not response:
            return None
        try:
            state = json.loads(response)
        except json.JSONDecodeError:
            return None
        return state if isinstance(state, dict) else None

    def set_manual_duty(self, duty: int) -> bool:
        """Activates manual mode on the daemon with the specified duty cycle."""
        if not 0 <= duty <= 100:
            raise ValueError("duty must be between 0 and 100")
        return self.send_command(f"SET {duty}") == "OK"

    def resume(self) -> bool:
        """Requests the daemon to resume automatic fan control."""
        return self.send_command("RESUME") == "OK"
