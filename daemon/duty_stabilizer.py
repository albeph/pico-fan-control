#!/usr/bin/env python3
"""
duty_stabilizer.py - Fan Duty Cycle Anti-Hunting & Stabilization
================================================================
Prevents rapid fan fluctuation ("fan hunting" / "sawtooth jitter")
caused by sudden and brief CPU temperature spikes.

Implements a 2-phase asymmetric stabilization curve:
  1. Fast attack: Any increase in target duty cycle is applied IMMEDIATELY
     to guarantee hardware thermal safety.
  2. Step-Down Hold (Phase 1): When target duty drops, the current duty
     is held for a configurable duration (default: 10 seconds).
     If temperature spikes again during this hold window, the hold is
     aborted and the fan remains at or goes to the higher speed.
  3. Gradual Ramp-Down (Phase 2): Once the hold time expires and temperature
     remains low, duty cycle is decremented smoothly by a configurable
     percentage (e.g. 10% per interval) until reaching the target step.
"""

from __future__ import annotations

import time
from typing import Optional


class DutyStabilizer:
    """
    Stabilizes duty cycle transitions to eliminate rapid toggling.
    """

    def __init__(
        self,
        hold_seconds: float = 10.0,
        ramp_step: int = 10,
        initial_duty: int = -1,
    ):
        """
        :param hold_seconds: Seconds to maintain higher duty before decreasing.
                             Set to 0 to disable hold delay.
        :param ramp_step: Maximum percentage points to decrease per update cycle
                          after hold expires. Set to >= 100 to disable gradual ramping.
        :param initial_duty: Initial duty cycle (-1 if not yet initialized).
        """
        self.hold_seconds: float = max(0.0, float(hold_seconds))
        self.ramp_step: int = max(1, int(ramp_step))
        self.current_duty: int = initial_duty
        self.target_duty: int = initial_duty if initial_duty >= 0 else 0
        self.hold_start_time: Optional[float] = None
        self._last_now: Optional[float] = None
        self._is_simulated: bool = False

    def _get_now(self) -> float:
        if self._is_simulated and self._last_now is not None:
            return self._last_now
        return time.monotonic()

    def reset(self, duty: int = 0) -> None:
        """Resets all timers and forces the current duty cycle."""
        self.current_duty = duty
        self.target_duty = duty
        self.hold_start_time = None

    @property
    def is_holding(self) -> bool:
        """Returns True if currently in Phase 1 (holding higher duty)."""
        if self.hold_seconds <= 0 or self.hold_start_time is None:
            return False
        if self.target_duty >= self.current_duty:
            return False
        elapsed = self._get_now() - self.hold_start_time
        return elapsed < self.hold_seconds

    @property
    def hold_remaining(self) -> float:
        """Returns remaining hold time in seconds, or 0.0."""
        if not self.is_holding or self.hold_start_time is None:
            return 0.0
        elapsed = self._get_now() - self.hold_start_time
        return max(0.0, self.hold_seconds - elapsed)

    @property
    def is_ramping(self) -> bool:
        """Returns True if currently in Phase 2 (actively ramping down)."""
        return (not self.is_holding) and (self.target_duty < self.current_duty)

    def update(self, raw_target: int, now: Optional[float] = None) -> int:
        """
        Processes a raw target duty cycle reading and returns the stabilized duty cycle.

        :param raw_target: Instantaneous target duty requested by sensor/adapter (0-100).
        :param now: Optional monotonic timestamp (useful for deterministic unit testing).
        :return: Stabilized duty cycle (0-100).
        """
        if now is not None:
            self._is_simulated = True
            self._last_now = now
        else:
            self._is_simulated = False
            now = time.monotonic()
            self._last_now = now

        raw_target = max(0, min(100, int(raw_target)))
        self.target_duty = raw_target

        # First update / uninitialized
        if self.current_duty < 0:
            self.current_duty = raw_target
            self.hold_start_time = None
            return self.current_duty

        # -------------------------------------------------------------------
        # Rule 1: Fast Attack on Increase / Equal
        # -------------------------------------------------------------------
        if raw_target >= self.current_duty:
            # Immediate response to rise in temperature
            self.current_duty = raw_target
            self.hold_start_time = None
            return self.current_duty

        # -------------------------------------------------------------------
        # Rule 2: Step-Down requested (raw_target < self.current_duty)
        # -------------------------------------------------------------------
        # Start hold timer if not already running
        if self.hold_start_time is None:
            self.hold_start_time = now

        elapsed = now - self.hold_start_time

        # Phase 1: Hold current duty
        if self.hold_seconds > 0 and elapsed < self.hold_seconds:
            return self.current_duty

        # Phase 2: Hold expired -> Ramp down
        if self.ramp_step >= 100:
            # Direct step down without ramping
            self.current_duty = raw_target
            self.hold_start_time = None
        else:
            # Gradual decrement by ramp_step
            new_duty = max(raw_target, self.current_duty - self.ramp_step)
            self.current_duty = new_duty
            if self.current_duty == raw_target:
                # Finished reaching target
                self.hold_start_time = None

        return self.current_duty
