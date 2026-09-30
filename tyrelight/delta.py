"""Live delta to your best lap, computed from AC's normalised track position.

Original Assetto Corsa does not publish a delta in shared memory (ACC does), so
we record (position, elapsed ms) samples through each lap and, once a lap is
completed with a new personal best, use it as the reference trace.
"""
from __future__ import annotations

from bisect import bisect_left

from .ac_shared_memory import Snapshot


class DeltaTracker:
    def __init__(self) -> None:
        self._reference_pos: list[float] = []
        self._reference_ms: list[int] = []
        self._current_pos: list[float] = []
        self._current_ms: list[int] = []
        self._last_laps = -1
        self._last_pos = 0.0
        self.reference_lap_ms: int | None = None
        self.delta_ms: float | None = None

    def update(self, s: Snapshot) -> float | None:
        if not s.live:
            return self.delta_ms

        lap_finished = s.completed_laps != self._last_laps and self._last_laps >= 0
        if lap_finished:
            self._finish_lap(s)
        elif s.normalized_pos < self._last_pos - 0.5:
            # Wrapped from ~1.0 to ~0.0 without completedLaps changing (e.g. the
            # first timed lap or an invalidated lap): just start a fresh trace.
            self._current_pos, self._current_ms = [], []
        self._last_laps = s.completed_laps
        self._last_pos = s.normalized_pos

        if s.in_pit:
            self._current_pos, self._current_ms = [], []
            self.delta_ms = None
            return None

        if not self._current_pos or s.normalized_pos > self._current_pos[-1]:
            self._current_pos.append(s.normalized_pos)
            self._current_ms.append(s.current_time_ms)

        if not self._reference_pos or s.current_time_ms <= 0:
            self.delta_ms = None
            return None

        ref_ms = self._interp(s.normalized_pos)
        self.delta_ms = s.current_time_ms - ref_ms
        return self.delta_ms

    def _finish_lap(self, s: Snapshot) -> None:
        # A lap that started mid-track has a short trace and would make a bad
        # reference; require samples that span most of the lap.
        complete = self._current_pos and self._current_pos[0] < 0.05 and self._current_pos[-1] > 0.95
        best = s.last_time_ms > 0 and (self.reference_lap_ms is None or s.last_time_ms < self.reference_lap_ms)
        if complete and best:
            self._reference_pos = self._current_pos + [1.0]
            self._reference_ms = self._current_ms + [s.last_time_ms]
            self.reference_lap_ms = s.last_time_ms
        self._current_pos, self._current_ms = [], []

    def _interp(self, pos: float) -> float:
        xs, ys = self._reference_pos, self._reference_ms
        i = bisect_left(xs, pos)
        if i <= 0:
            return ys[0]
        if i >= len(xs):
            return ys[-1]
        x0, x1, y0, y1 = xs[i - 1], xs[i], ys[i - 1], ys[i]
        if x1 == x0:
            return y1
        return y0 + (y1 - y0) * (pos - x0) / (x1 - x0)
