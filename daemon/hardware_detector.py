#!/usr/bin/env python3
"""
hardware_detector.py - Raspberry Pi Pico / RP2040 Hardware Detection
======================================================================
Responsible for:
  - Scanning /dev/serial/by-id/ for connected RP2040 / Pico devices
  - Probing serial communication to verify responsiveness to "RPM"
  - Providing stable, unique paths based on persistent hardware identifiers
"""

from __future__ import annotations

import os
import glob
import time
import logging
from pathlib import Path
from typing import Optional

try:
    import serial.serialutil
    from pico_adapter import PicoAdapter
except ImportError:
    raise SystemExit(
        "Errore: pyserial non installato. Eseguire: pip install pyserial"
    )

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
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
SERIAL_TIMEOUT  = 2.0       # seconds
PROBE_RETRIES   = 3


# ---------------------------------------------------------------------------
# Dataclass-like container for a detected device
# ---------------------------------------------------------------------------
class PicoDevice:
    """Represents a detected Raspberry Pi Pico on a serial port."""

    def __init__(
        self,
        by_id_path: str,
        real_path: str,
        hw_id: str,
        rpm: Optional[int] = None,
        duty: Optional[int] = None,
        responsive: bool = False,
    ):
        self.by_id_path  = by_id_path   # Stable persistent path in /dev/serial/by-id/
        self.real_path   = real_path    # Real resolved path (e.g. /dev/ttyACM0)
        self.hw_id       = hw_id        # Unique hardware ID (symlink basename)
        self.rpm         = rpm
        self.duty        = duty
        self.responsive  = responsive

    def __repr__(self) -> str:
        status = f"RPM={self.rpm} DUTY={self.duty}%" if self.responsive else "not responding"
        return (
            f"PicoDevice(id='{self.hw_id}', "
            f"port='{self.real_path}', "
            f"{status})"
        )


# ---------------------------------------------------------------------------
# Main detection functions
# ---------------------------------------------------------------------------

def list_serial_by_id() -> list[str]:
    """
    Returns all entry paths in /dev/serial/by-id/.
    Returns an empty list if the directory does not exist (no serial devices).
    """
    base = Path(SERIAL_BY_ID_PATH)
    if not base.exists():
        logger.debug("Directory %s non trovata", SERIAL_BY_ID_PATH)
        return []
    return [str(p) for p in base.iterdir()]


def is_pico_device(by_id_path: str) -> bool:
    """
    Determines whether a /dev/serial/by-id/ path corresponds to a Pico/RP2040
    by matching known hardware keywords in its name.
    """
    name = os.path.basename(by_id_path)
    for kw in PICO_KEYWORDS:
        if kw in name:
            return True
    return False


def resolve_real_path(by_id_path: str) -> Optional[str]:
    """
    Resolves the /dev/serial/by-id/ symlink to the real device node path.
    Returns None if the symlink is broken (device disconnected).
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
    Opens serial port and sends 'RPM' command to test protocol response.

    Returns:
        (responsive, rpm, duty) tuple.
    """
    for attempt in range(PROBE_RETRIES):
        try:
            with PicoAdapter(real_path, timeout=SERIAL_TIMEOUT) as pico:
                rpm, duty = pico.fetch_rpm()
                logger.debug("Risposta da %s: RPM=%s DUTY=%s", real_path, rpm, duty)
                if rpm is not None:
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


def scan_devices(probe: bool = True) -> list[PicoDevice]:
    """
    Scans /dev/serial/by-id/ and returns a list of PicoDevice objects.

    Args:
        probe: If True, tests serial communication for each detected device.

    Returns:
        List of detected PicoDevice objects (may be empty).
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
    Checks whether the device configured in config.json is still present
    and reachable. Returns real device path or None.
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
