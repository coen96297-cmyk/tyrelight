"""Tyre condition classification and the LED layout that displays it."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .ac_shared_memory import Snapshot


class Condition(str, Enum):
    COLD = "cold"
    IDEAL = "ideal"
    HOT = "hot"
    OVERHEATED = "overheated"


# LED colours per condition (R, G, B). Dark blue for cold so it is clearly
# different from green at a glance, amber for "watch it", red for "back off".
LED_COLOURS: dict[Condition, tuple[int, int, int]] = {
    Condition.COLD: (0, 40, 255),
    Condition.IDEAL: (0, 255, 0),
    Condition.HOT: (255, 120, 0),
    Condition.OVERHEATED: (255, 0, 0),
}

SEVERITY: dict[Condition, float] = {
    Condition.IDEAL: 0.0,
    Condition.COLD: 0.35,
    Condition.HOT: 0.7,
    Condition.OVERHEATED: 1.0,
}


@dataclass(frozen=True)
class TempWindow:
    """Core-temperature bands in Celsius: ``cold_below`` .. ``ideal`` .. ``hot_above`` .. ``overheat_above``."""

    cold_below: float
    hot_above: float
    overheat_above: float

    def classify(self, core_temp: float) -> Condition:
        if core_temp >= self.overheat_above:
            return Condition.OVERHEATED
        if core_temp >= self.hot_above:
            return Condition.HOT
        if core_temp < self.cold_below:
            return Condition.COLD
        return Condition.IDEAL


# Reasonable defaults per compound family. Tune in config.json for your car;
# the compound string comes straight from AC's graphics page.
DEFAULT_WINDOWS: dict[str, TempWindow] = {
    "slick": TempWindow(cold_below=80, hot_above=105, overheat_above=115),
    "semislick": TempWindow(cold_below=75, hot_above=100, overheat_above=110),
    "street": TempWindow(cold_below=60, hot_above=90, overheat_above=100),
    "vintage": TempWindow(cold_below=60, hot_above=85, overheat_above=95),
    "rain": TempWindow(cold_below=40, hot_above=70, overheat_above=80),
    "default": TempWindow(cold_below=70, hot_above=100, overheat_above=110),
}


def window_for(compound: str, windows: dict[str, TempWindow] | None = None) -> TempWindow:
    windows = windows or DEFAULT_WINDOWS
    name = (compound or "").lower()
    # Exact compound names (e.g. "Soft (S)") take priority over families.
    for key, win in windows.items():
        if key != "default" and key.lower() == name:
            return win
    for family in ("semislick", "slick", "street", "vintage", "rain"):
        if family in name and family in windows:
            return windows[family]
    if any(tag in name for tag in ("soft", "medium", "hard", "supersoft", "hypersoft")) and "slick" in windows:
        return windows["slick"]
    return windows.get("default", DEFAULT_WINDOWS["default"])


@dataclass
class TyreState:
    conditions: list[Condition]          # FL, FR, RL, RR
    worst: Condition
    severity: float                      # 0 = everything ideal, 1 = something overheated
    window: TempWindow


def assess(snapshot: Snapshot, windows: dict[str, TempWindow] | None = None) -> TyreState:
    window = window_for(snapshot.compound, windows)
    conditions = [window.classify(t) for t in snapshot.tyre_core]
    worst = max(conditions, key=lambda c: SEVERITY[c])
    return TyreState(conditions, worst, SEVERITY[worst], window)


# --------------------------------------------------------------------------- #
# LED layout
# --------------------------------------------------------------------------- #

# Left-to-right across the bar: front-left, rear-left, [centre], rear-right,
# front-right. So the LEDs sit roughly where the tyres are when you look
# down at the wheel: fronts on the outside edges, rears inboard.
LAYOUT_ORDER = (0, 2, 3, 1)  # indexes into (FL, FR, RL, RR)


def led_layout(led_count: int) -> list[int | None]:
    """Map each LED index to a tyre index (0..3) or None for centre LEDs."""
    per_tyre = led_count // 4
    centre = led_count - per_tyre * 4
    layout: list[int | None] = []
    layout += [LAYOUT_ORDER[0]] * per_tyre
    layout += [LAYOUT_ORDER[1]] * per_tyre
    layout += [None] * centre
    layout += [LAYOUT_ORDER[2]] * per_tyre
    layout += [LAYOUT_ORDER[3]] * per_tyre
    return layout


def led_colours(state: TyreState, led_count: int, fuel_warning: bool = False) -> list[tuple[int, int, int]]:
    """Colour for every LED. Centre LEDs show a fuel warning (white) or stay dark."""
    out: list[tuple[int, int, int]] = []
    for tyre in led_layout(led_count):
        if tyre is None:
            out.append((255, 255, 255) if fuel_warning else (0, 0, 0))
        else:
            out.append(LED_COLOURS[state.conditions[tyre]])
    return out


def led_lit(state: TyreState, led_count: int, blink_phase: bool) -> list[bool]:
    """Overheated tyres blink (only their LEDs), everything else stays solid."""
    lit: list[bool] = []
    for tyre in led_layout(led_count):
        if tyre is not None and state.conditions[tyre] is Condition.OVERHEATED:
            lit.append(blink_phase)
        else:
            lit.append(True)
    return lit
