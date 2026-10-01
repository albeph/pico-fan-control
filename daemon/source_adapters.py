#!/usr/bin/env python3
"""
source_adapters.py - Control Source Adapters for pico-fan-control
================================================================
Provides a unified Adapter interface for different input sources
(internal fan RPM, temperature sensors, etc.) to drive external fan control.

Each adapter encapsulates:
  1. Hardware reading (read)
  2. Fan curve calculation (compute_duty)
  3. Value formatting for logging and UI (format_value)
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Optional

logger = logging.getLogger("fan_daemon")


class SourceAdapter(ABC):
    """
    Abstract Base Class for fan control input sources.
    Defines the contract required by FanDaemon.
    """

    def __init__(self, config: dict):
        self.config = config

    @property
    @abstractmethod
    def name(self) -> str:
        """Identifier for the control source (e.g. 'rpm', 'temp')."""

    @property
    @abstractmethod
    def unit(self) -> str:
        """Unit of measurement (e.g. 'RPM', '°C')."""

    @abstractmethod
    def read(self) -> float:
        """
        Reads current value from the hardware source.
        Returns numerical reading (e.g. RPM or °C).
        """

    @abstractmethod
    def compute_duty(self, value: float) -> int:
        """
        Computes target duty cycle (0-100) based on value and thresholds.
        """

    @abstractmethod
    def format_value(self, value: float) -> str:
        """Returns a formatted string representing the value with unit."""

    @staticmethod
    def _compute_stepped_duty(
        value: float,
        thr_high: float,
        thr_mid: float,
        d_high: int,
        d_mid: int,
        d_low: int,
    ) -> int:
        """Standard 3-step duty curve applied across sources."""
        if value > thr_high:
            return d_high
        elif value >= thr_mid:
            return d_mid
        else:
            return d_low


class RpmSourceAdapter(SourceAdapter):
    """
    Adapter for monitoring internal fan RPM (via hwmon or ThinkPad ACPI).
    """

    @property
    def name(self) -> str:
        return "rpm"

    @property
    def unit(self) -> str:
        return "RPM"

    def read(self) -> float:
        # Import lazily to avoid circular imports
        from fan_daemon import read_internal_rpm
        return float(read_internal_rpm(self.config))

    def compute_duty(self, value: float) -> int:
        high_thr = self.config.get("rpm_threshold_high", 4000)
        mid_thr  = self.config.get("rpm_threshold_mid",  2500)
        d_high   = self.config.get("duty_high",           100)
        d_mid    = self.config.get("duty_mid",            50)
        d_low    = self.config.get("duty_low",            0)
        return self._compute_stepped_duty(value, high_thr, mid_thr, d_high, d_mid, d_low)

    def format_value(self, value: float) -> str:
        return f"{int(value)} RPM"


class TempSourceAdapter(SourceAdapter):
    """
    Adapter for monitoring system temperature sensors via hwmon.
    Supports temperature hysteresis to eliminate boundary jitter.
    """

    def __init__(self, config: dict):
        super().__init__(config)
        self._last_duty: Optional[int] = None

    @property
    def name(self) -> str:
        return "temp"

    @property
    def unit(self) -> str:
        return "°C"

    def read(self) -> float:
        from temp_reader import read_temperature
        temp = read_temperature(self.config)
        return float(temp) if temp is not None else 0.0

    def compute_duty(self, value: float) -> int:
        high_thr = float(self.config.get("temp_threshold_high", 80))
        mid_thr  = float(self.config.get("temp_threshold_mid",  60))
        d_high   = int(self.config.get("duty_high",           100))
        d_mid    = int(self.config.get("duty_mid",            50))
        d_low    = int(self.config.get("duty_low",            0))
        hyst     = float(self.config.get("temp_hysteresis",    3))

        # If hysteresis is disabled or no previous duty was recorded
        if hyst <= 0 or self._last_duty is None:
            duty = self._compute_stepped_duty(value, high_thr, mid_thr, d_high, d_mid, d_low)
            self._last_duty = duty
            return duty

        # Apply hysteresis based on the current state
        if self._last_duty == d_high:
            if value < (high_thr - hyst):
                duty = d_low if value < (mid_thr - hyst) else d_mid
            else:
                duty = d_high
        elif self._last_duty == d_mid:
            if value > high_thr:
                duty = d_high
            elif value < (mid_thr - hyst):
                duty = d_low
            else:
                duty = d_mid
        else:
            if value > high_thr:
                duty = d_high
            elif value >= mid_thr:
                duty = d_mid
            else:
                duty = d_low

        self._last_duty = duty
        return duty

    def format_value(self, value: float) -> str:
        return f"{value:.1f}°C"


def get_source_adapter(config: dict) -> SourceAdapter:
    """
    Factory function returning the appropriate SourceAdapter for the given configuration.
    """
    source_type = config.get("control_source", "rpm").lower()
    if source_type == "temp":
        return TempSourceAdapter(config)
    return RpmSourceAdapter(config)
