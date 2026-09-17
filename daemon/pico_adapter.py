"""
pico_adapter.py - Shared Serial Protocol Adapter for Raspberry Pi Pico
========================================================================
Acts as the communication and protocol translation layer between the host
pico-fan software (daemon, wizard, test scripts) and the MicroPython firmware
running on the Raspberry Pi Pico / RP2040.
"""

from __future__ import annotations

import logging
import time
from typing import Optional

try:
    import serial
    import serial.serialutil
except ImportError:
    raise SystemExit("Errore: pyserial non installato. pip install pyserial")


logger = logging.getLogger(__name__)

BAUDRATE = 115200
DEFAULT_TIMEOUT = 2.0
CONNECT_DELAY = 0.5


class PicoAdapter:
    """Manages connection and command dispatching for the pico-fan serial protocol."""

    def __init__(
        self,
        port: str,
        timeout: float = DEFAULT_TIMEOUT,
        connect_delay: float = CONNECT_DELAY,
    ) -> None:
        self.port = port
        self.timeout = timeout
        self.connect_delay = connect_delay
        self._serial: Optional[serial.Serial] = None

    @property
    def connected(self) -> bool:
        """Returns True if the serial port is currently open."""
        return self._serial is not None

    def connect(self) -> None:
        """Opens the serial port and waits until the Pico's USB CDC is ready."""
        if self.connected:
            return

        connection = serial.Serial(
            self.port,
            baudrate=BAUDRATE,
            timeout=self.timeout,
        )
        time.sleep(self.connect_delay)
        connection.reset_input_buffer()
        self._serial = connection

    def disconnect(self) -> None:
        """Closes the serial port without raising on closure errors."""
        if self._serial is None:
            return
        try:
            self._serial.close()
        except (serial.serialutil.SerialException, OSError):
            pass
        finally:
            self._serial = None

    def send_command(self, command: str) -> Optional[str]:
        """Sends a line-based command and returns the response, if available."""
        if self._serial is None:
            return None

        try:
            self._serial.reset_input_buffer()
            self._serial.write((command + "\n").encode("ascii"))
            self._serial.flush()
            return self._serial.readline().decode("ascii", errors="replace").strip()
        except (serial.serialutil.SerialException, OSError) as exc:
            logger.warning("Errore comunicazione seriale con %s: %s", self.port, exc)
            self.disconnect()
            return None

    def set_duty(self, duty: int) -> bool:
        """Sets the external fan duty cycle percentage (0-100)."""
        if not 0 <= duty <= 100:
            raise ValueError("duty must be between 0 and 100")
        return self.send_command(f"SET {duty}") == "OK"

    def fetch_rpm(self) -> tuple[Optional[int], Optional[int]]:
        """Queries current RPM and duty cycle, returning (rpm, duty)."""
        response = self.send_command("RPM")
        if not response or not response.startswith("RPM:"):
            return None, None

        rpm = None
        duty = None
        try:
            for token in response.split():
                if token.startswith("RPM:"):
                    rpm = int(token[4:])
                elif token.startswith("DUTY:"):
                    duty = int(token[5:].rstrip("%"))
        except ValueError:
            return None, None
        return rpm, duty

    def __enter__(self) -> "PicoAdapter":
        self.connect()
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.disconnect()
