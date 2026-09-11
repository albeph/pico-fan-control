"""Client condiviso per il protocollo seriale del Raspberry Pi Pico.
Funge da layer di traduzione tra il software pico-fan (Solitamente dal deamon) ed i comandi del microcontrollore
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
    """Gestisce connessione e comandi del protocollo pico-fan."""

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
        """Indica se la porta seriale è attualmente aperta."""
        return self._serial is not None

    def connect(self) -> None:
        """Apre la porta seriale e attende che il CDC del Pico sia pronto."""
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
        """Chiude la porta seriale senza propagare errori di chiusura."""
        if self._serial is None:
            return
        try:
            self._serial.close()
        except (serial.serialutil.SerialException, OSError):
            pass
        finally:
            self._serial = None

    def send_command(self, command: str) -> Optional[str]:
        """Invia un comando line-based e restituisce la risposta, se presente."""
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
        """Imposta il duty cycle della ventola esterna."""
        if not 0 <= duty <= 100:
            raise ValueError("duty deve essere compreso tra 0 e 100")
        return self.send_command(f"SET {duty}") == "OK"

    def fetch_rpm(self) -> tuple[Optional[int], Optional[int]]:
        """Richiede RPM e duty correnti, restituendo ``(rpm, duty)``."""
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
