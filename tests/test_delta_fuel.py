import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from tyrelight.ac_shared_memory import Snapshot  # noqa: E402
from tyrelight.delta import DeltaTracker  # noqa: E402
from tyrelight.fuel import FuelTracker  # noqa: E402


def drive_lap(tracker, lap_index, lap_ms, steps=50):
    for i in range(steps):
        pos = i / steps
        tracker.update(Snapshot(live=True, completed_laps=lap_index, normalized_pos=pos,
                                current_time_ms=int(pos * lap_ms)))


def test_delta_uses_best_completed_lap_as_reference():
    t = DeltaTracker()
    drive_lap(t, 0, 90_000)
    # Lap 0 completes at 90.0 s
    t.update(Snapshot(live=True, completed_laps=1, normalized_pos=0.0, current_time_ms=0, last_time_ms=90_000))
    assert t.reference_lap_ms == 90_000
    # Half way round the next lap, 1 s slower than reference pace
    d = t.update(Snapshot(live=True, completed_laps=1, normalized_pos=0.5, current_time_ms=46_000, last_time_ms=90_000))
    assert d is not None and abs(d - 1000) < 60


def test_delta_ignores_partial_first_lap():
    t = DeltaTracker()
    for i in range(30, 50):
        t.update(Snapshot(live=True, completed_laps=0, normalized_pos=i / 50, current_time_ms=i * 1000))
    t.update(Snapshot(live=True, completed_laps=1, normalized_pos=0.0, current_time_ms=0, last_time_ms=50_000))
    assert t.reference_lap_ms is None


def test_fuel_per_lap_and_laps_left():
    f = FuelTracker()
    f.update(Snapshot(live=True, completed_laps=0, fuel=50.0, max_fuel=100))
    f.update(Snapshot(live=True, completed_laps=1, fuel=47.0, max_fuel=100))
    f.update(Snapshot(live=True, completed_laps=2, fuel=44.0, max_fuel=100))
    assert f.per_lap == 3.0
    assert f.laps_left is not None and abs(f.laps_left - 44 / 3) < 1e-6
