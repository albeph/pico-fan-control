"""Adapter client per il socket IPC del demone pico-fan.
Permette ai vari script python di interfacciarsi con il demone gestito da fan_deamon
"""

from __future__ import annotations

import json
import socket
from typing import Any


SOCK_PATH = "/run/pico-fan.sock"
DEFAULT_TIMEOUT = 3.0


class IpcAdapter:
    """Invia comandi al demone e converte le risposte del socket."""

    def __init__(self, socket_path: str = SOCK_PATH, timeout: float = DEFAULT_TIMEOUT) -> None:
        self.socket_path = socket_path
        self.timeout = timeout

    def send_command(self, command: str = "") -> str | None:
        """Invia un comando IPC e restituisce la risposta line-based."""
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
        """Richiede lo stato corrente del demone."""
        response = self.send_command()
        if not response:
            return None
        try:
            state = json.loads(response)
        except json.JSONDecodeError:
            return None
        return state if isinstance(state, dict) else None

    def set_manual_duty(self, duty: int) -> bool:
        """Attiva la modalità manuale del demone con il duty indicato."""
        if not 0 <= duty <= 100:
            raise ValueError("duty deve essere compreso tra 0 e 100")
        return self.send_command(f"SET {duty}") == "OK"

    def resume(self) -> bool:
        """Chiede al demone di ripristinare il controllo automatico."""
        return self.send_command("RESUME") == "OK"
