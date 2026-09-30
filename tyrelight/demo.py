"""Synthetic telemetry so the overlay and LEDs can be exercised without AC.

Drives a fake lap around a 90-second circuit: tyres warm up from cold, the
fronts go over the top in the fast corners, fuel burns down, and the delta
wanders around a best lap. Good for demos, README GIFs, and testing the LED
mapping on the wheel without launching the game.
"""
from __future__ import annotations

import math
import time

from .ac_shared_memory import AC_LIVE, Snapshot


class DemoSource:
    LAP_SECONDS = 90.0

    def __init__(self, speed: float = 1.0) -> None:
        self._t0 = time.monotonic()
        self._speed = speed
        self._best_ms = 90_400
        self._last_ms = 0

    def read(self) -> Snapshot:
        t = (time.monotonic() - self._t0) * self._speed
        lap_no, lap_t = divmod(t, self.LAP_SECONDS)
        laps_done = int(lap_no)
        # Per-lap pace wobble so the delta to best is not a flat zero: a small
        # phase-shifted sine keeps position monotonic within the lap.
        wobble = 0.012 * math.sin(2 * math.pi * lap_t / self.LAP_SECONDS + laps_done * 1.7)
        pos = min(0.9999, max(0.0, lap_t / self.LAP_SECONDS + wobble))

        # Warm-up curve over the first ~2 laps, then a per-corner oscillation.
        warm = 1 - math.exp(-t / 70.0)
        corner = 0.5 + 0.5 * math.sin(pos * 2 * math.pi * 6)      # six "corners"
        long_cycle = 0.5 + 0.5 * math.sin(t / 45.0)                # slow drift
        base = 35 + 60 * warm
        fl = base + 14 * corner + 14 * long_cycle
        fr = base + 10 * corner + 6 * long_cycle
        rl = base + 6 * corner
        rr = base + 5 * corner + 3 * long_cycle
        core = [fl, fr, rl, rr]

        speed = 120 + 130 * (0.5 + 0.5 * math.sin(pos * 2 * math.pi * 3))
        rpm = int(3500 + 4500 * (0.5 + 0.5 * math.sin(pos * 2 * math.pi * 12)))
        gear = 2 + int(4 * (speed - 120) / 130)

        lap_ms = int(lap_t * 1000)
        if laps_done > 0 and lap_t < 0.05:
            self._last_ms = int((self.LAP_SECONDS + 0.6 * math.sin(laps_done)) * 1000)
            self._best_ms = min(self._best_ms, self._last_ms)

        return Snapshot(
            live=True,
            status=AC_LIVE,
            car="ks_porsche_911_gt3_cup_2017",
            track="ks_nordschleife",
            compound="Slick (M)",
            speed_kmh=speed,
            rpm=rpm,
            max_rpm=8500,
            gear=gear,
            fuel=max(0.0, 62.0 - t * 2.9 / self.LAP_SECONDS),
            max_fuel=100.0,
            tyre_core=core,
            tyre_inner=[c + 4 for c in core],
            tyre_middle=[c + 1 for c in core],
            tyre_outer=[c - 5 for c in core],
            tyre_pressure=[26.5 + (c - 80) * 0.03 for c in core],
            tyre_wear=[max(0.0, 100 - t * 0.02 * (1 + i * 0.1)) for i in range(4)],
            brake_temp=[300 + 200 * corner] * 4,
            completed_laps=laps_done,
            current_time_ms=lap_ms,
            last_time_ms=self._last_ms,
            best_time_ms=self._best_ms,
            normalized_pos=pos,
            in_pit=False,
            air_temp=24.0,
            road_temp=31.0,
        )

    def close(self) -> None:
        pass
