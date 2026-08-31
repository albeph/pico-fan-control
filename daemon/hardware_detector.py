#!/usr/bin/env python3
"""
hardware_detector.py - Rilevamento hardware Raspberry Pi Pico / RP2040
=======================================================================
Modulo responsabile di:
  - Scansionare /dev/serial/by-id/ cercando dispositivi RP2040/Pico
  - Verificare la risposta al protocollo seriale (comando "RPM")
  - Restituire path univoci e stabili basati su ID hardware

Autore:   pico-fan-control project
Versione: 1.0.0
"""

from __future__ import annotations

import os
import glob
import time
import logging
from pathlib import Path
from typing import Optional

try:
    import serial
    import serial.serialutil
except ImportError:
    raise SystemExit(
        "Errore: pyserial non installato. Eseguire: pip install pyserial"
    )

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Costanti
# ---------------------------------------------------------------------------
SERIAL_BY_ID_PATH = "/dev/serial/by-id"
PICO_KEYWORDS = [
    "Raspberry_Pi",
    "Pico",
    "RP2040",
    "MicroPython",
    "raspberry_pi",
    "rp2040",
    "micropython",
]
SERIAL_BAUDRATE = 115200
SERIAL_TIMEOUT  = 2.0       # secondi
PROBE_RETRIES   = 3


# ---------------------------------------------------------------------------
# Dataclass-like per un dispositivo rilevato
# ---------------------------------------------------------------------------
class PicoDevice:
    """Rappresenta un Raspberry Pi Pico rilevato sulla porta seriale."""

    def __init__(
        self,
        by_id_path: str,
        real_path: str,
        hw_id: str,
        rpm: Optional[int] = None,
        duty: Optional[int] = None,
        responsive: bool = False,
    ):
        self.by_id_path  = by_id_path   # Path stabile in /dev/serial/by-id/
        self.real_path   = real_path    # Path reale (es. /dev/ttyACM0)
        self.hw_id       = hw_id        # ID hardware univoco (basename del symlink)
        self.rpm         = rpm
        self.duty        = duty
        self.responsive  = responsive

    def __repr__(self) -> str:
        status = f"RPM={self.rpm} DUTY={self.duty}%" if self.responsive else "non risponde"
        return (
            f"PicoDevice(id='{self.hw_id}', "
            f"port='{self.real_path}', "
            f"{status})"
        )


# ---------------------------------------------------------------------------
# Funzioni principali
# ---------------------------------------------------------------------------

def list_serial_by_id() -> list[str]:
    """
    Restituisce tutti i path in /dev/serial/by-id/.
    Ritorna lista vuota se la directory non esiste (nessun dispositivo seriale).
    """
    base = Path(SERIAL_BY_ID_PATH)
    if not base.exists():
        logger.debug("Directory %s non trovata", SERIAL_BY_ID_PATH)
        return []
    return [str(p) for p in base.iterdir()]


def is_pico_device(by_id_path: str) -> bool:
    """
    Determina se un percorso /dev/serial/by-id/ corrisponde a un Pico/RP2040
    verificando le keyword nel nome.
    """
    name = os.path.basename(by_id_path)
    for kw in PICO_KEYWORDS:
        if kw in name:
            return True
    return False


def resolve_real_path(by_id_path: str) -> Optional[str]:
    """
    Risolve il symlink di /dev/serial/by-id/ verso il path reale del device.
    Ritorna None se il symlink è rotto (dispositivo scollegato).
    """
    try:
        real = os.path.realpath(by_id_path)
        if os.path.exists(real):
            return real
    except OSError as exc:
        logger.debug("Impossibile risolvere %s: %s", by_id_path, exc)
    return None


def probe_pico(real_path: str) -> tuple[bool, Optional[int], Optional[int]]:
    """
    Apre la porta seriale e invia il comando "RPM" per verificare la risposta.

    Returns:
        (responsive, rpm, duty) tuple.
    """
    for attempt in range(PROBE_RETRIES):
        try:
            with serial.Serial(
                real_path,
                baudrate=SERIAL_BAUDRATE,
                timeout=SERIAL_TIMEOUT,
            ) as ser:
                time.sleep(0.5)         # Attende reset CDC
                ser.reset_input_buffer()
                ser.write(b"RPM\n")
                ser.flush()
                response = ser.readline().decode("ascii", errors="replace").strip()

                logger.debug("Risposta da %s: '%s'", real_path, response)

                if response.startswith("RPM:"):
                    rpm, duty = _parse_rpm_response(response)
                    return True, rpm, duty

        except serial.serialutil.SerialException as exc:
            logger.debug(
                "Tentativo %d/%d su %s fallito: %s",
                attempt + 1, PROBE_RETRIES, real_path, exc
            )
            time.sleep(0.3)
        except Exception as exc:  # pylint: disable=broad-except
            logger.warning("Errore inatteso su %s: %s", real_path, exc)
            break

    return False, None, None


def _parse_rpm_response(response: str) -> tuple[Optional[int], Optional[int]]:
    """
    Parsa la risposta "RPM:<val> DUTY:<val>%" e restituisce (rpm, duty).
    """
    rpm = None
    duty = None
    try:
        parts = response.split()
        for part in parts:
            if part.startswith("RPM:"):
                rpm = int(part[4:])
            elif part.startswith("DUTY:"):
                duty = int(part[5:].rstrip("%"))
    except (ValueError, IndexError) as exc:
        logger.debug("Errore parsing risposta '%s': %s", response, exc)
    return rpm, duty


def scan_devices(probe: bool = True) -> list[PicoDevice]:
    """
    Scansiona /dev/serial/by-id/ e restituisce lista di PicoDevice.

    Args:
        probe: Se True, testa la risposta seriale di ogni dispositivo trovato.

    Returns:
        Lista di PicoDevice rilevati (può essere vuota).
    """
    found: list[PicoDevice] = []

    all_entries = list_serial_by_id()
    pico_entries = [e for e in all_entries if is_pico_device(e)]

    if not pico_entries:
        logger.info("Nessun dispositivo Pico/RP2040 trovato in %s", SERIAL_BY_ID_PATH)
        return found

    for by_id_path in pico_entries:
        hw_id = os.path.basename(by_id_path)
        real_path = resolve_real_path(by_id_path)

        if real_path is None:
            logger.warning("Symlink rotto: %s (dispositivo scollegato?)", by_id_path)
            continue

        logger.info("Dispositivo trovato: %s -> %s", hw_id, real_path)

        responsive, rpm, duty = False, None, None
        if probe:
            responsive, rpm, duty = probe_pico(real_path)
            if responsive:
                logger.info("  -> Risponde al protocollo: RPM=%s DUTY=%s%%", rpm, duty)
            else:
                logger.warning("  -> Non risponde al protocollo pico-fan")

        found.append(PicoDevice(
            by_id_path=by_id_path,
            real_path=real_path,
            hw_id=hw_id,
            rpm=rpm,
            duty=duty,
            responsive=responsive,
        ))

    return found


def find_configured_device(config_path: str) -> Optional[str]:
    """
    Verifica se il dispositivo configurato in config.json è ancora presente
    e raggiungibile. Restituisce il path reale o None.
    """
    import json
    try:
        with open(config_path) as f:
            cfg = json.load(f)
        by_id = cfg.get("pico_serial_by_id", "")
        if not by_id:
            return None
        real = resolve_real_path(by_id)
        return real
    except (json.JSONDecodeError, FileNotFoundError, KeyError) as exc:
        logger.debug("Errore lettura configurazione %s: %s", config_path, exc)
        return None


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    devices = scan_devices(probe=True)
    if devices:
        print(f"\nDispositivi trovati: {len(devices)}")
        for dev in devices:
            print(f"  {dev}")
    else:
        print("Nessun dispositivo Pico trovato.")
