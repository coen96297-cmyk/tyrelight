"""Fuel-per-lap estimate and laps-remaining."""
from __future__ import annotations

from collections import deque

from .ac_shared_memory import Snapshot


class FuelTracker:
    def __init__(self, history: int = 5) -> None:
        self._laps: deque[float] = deque(maxlen=history)
        self._lap_start_fuel: float | None = None
        self._last_laps = -1
        self.per_lap: float | None = None
        self.laps_left: float | None = None

    def update(self, s: Snapshot) -> None:
        if not s.live:
            return
        if s.completed_laps != self._last_laps:
            if self._lap_start_fuel is not None and self._last_laps >= 0 and not s.in_pit:
                used = self._lap_start_fuel - s.fuel
                if 0 < used < s.max_fuel:  # ignore refuels / resets
                    self._laps.append(used)
            self._lap_start_fuel = s.fuel
            self._last_laps = s.completed_laps
        if s.in_pit:
            self._lap_start_fuel = None
        if self._laps:
            self.per_lap = sum(self._laps) / len(self._laps)
            self.laps_left = s.fuel / self.per_lap if self.per_lap > 0 else None
