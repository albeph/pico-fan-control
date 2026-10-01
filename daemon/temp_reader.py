#!/usr/bin/env python3
"""
temp_reader.py - Temperature Sensor Reader Module
===================================================
Reads system temperature from hwmon sysfs sensors and computes
target duty cycle based on configurable temperature thresholds.

Used as an alternative control source to the internal fan RPM.
Temperature files in /sys/class/hwmon/*/temp*_input contain
values in millidegrees Celsius (e.g. 52000 = 52°C).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger("fan_daemon")


# ===========================================================================
# Temperature sensor discovery
# ===========================================================================

def discover_temp_sensors() -> list[dict]:
    """
    Scans /sys/class/hwmon/*/temp*_input for available temperature sensors.

    Returns a list of dicts with keys:
        - 'name':  hwmon chip name (e.g. 'coretemp', 'thinkpad')
        - 'label': sensor label if available (e.g. 'Core 0', 'Package id 0')
        - 'path':  absolute path to the temp*_input file
        - 'temp':  current temperature in °C (float), or None if unreadable
    """
    sensors: list[dict] = []
    hwmon_base = Path("/sys/class/hwmon")

    if not hwmon_base.exists():
        return sensors

    for hwmon_dir in sorted(hwmon_base.iterdir()):
        # Read chip name
        try:
            chip_name = (hwmon_dir / "name").read_text().strip()
        except OSError:
            chip_name = hwmon_dir.name

        for temp_file in sorted(hwmon_dir.glob("temp*_input")):
            # Try to read label (e.g. temp1_label -> "Core 0")
            label_file = temp_file.with_name(
                temp_file.name.replace("_input", "_label")
            )
            try:
                label = label_file.read_text().strip()
            except OSError:
                label = temp_file.stem  # fallback: "temp1"

            # Read current temperature
            try:
                raw = int(temp_file.read_text().strip())
                temp_c = raw / 1000.0
            except (OSError, ValueError):
                temp_c = None

            sensors.append({
                "name":  chip_name,
                "label": label,
                "path":  str(temp_file),
                "temp":  temp_c,
            })

    return sensors


# ===========================================================================
# Temperature reading
# ===========================================================================

def read_temperature(config: dict) -> Optional[float]:
    """
    Reads temperature in °C from the configured hwmon sensor.

    If 'hwmon_temp_path' is set in config, reads only that file.
    Otherwise auto-discovers the first valid sensor.

    Returns temperature in °C, or None if no reading is available.
    """
    temp_path = config.get("hwmon_temp_path", "")

    if temp_path:
        # Read from explicitly configured path
        try:
            p = Path(temp_path)
            if not p.exists():
                logger.debug("Sensore temperatura %s non presente", temp_path)
                return None
            raw = int(p.read_text().strip())
            return raw / 1000.0
        except (OSError, ValueError) as exc:
            logger.debug("Errore lettura temperatura da %s: %s", temp_path, exc)
            return None

    # Auto-discover: return the first valid reading
    sensors = discover_temp_sensors()
    for sensor in sensors:
        if sensor["temp"] is not None:
            logger.debug(
                "Temperatura auto-rilevata da %s (%s): %.1f°C",
                sensor["path"], sensor["label"], sensor["temp"],
            )
            return sensor["temp"]

    return None


# ===========================================================================
# Temperature-based duty computation
# ===========================================================================

def compute_target_duty_temp(temp: float, config: dict) -> int:
    """
    Computes target duty cycle based on temperature and configured thresholds.
    Delegates to TempSourceAdapter.
    """
    from source_adapters import TempSourceAdapter
    return TempSourceAdapter(config).compute_duty(temp)
