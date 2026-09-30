"""Assetto Corsa shared-memory reader.

AC exposes three memory-mapped pages: ``acpmf_physics``, ``acpmf_graphics`` and
``acpmf_static``. The ctypes layouts below follow the official
"ACSharedMemoryDocumentation" (AC 1.16). Only the fields the overlay uses have
friendly accessors, but the full structs are declared so offsets stay correct.
"""
from __future__ import annotations

import ctypes
import mmap
import sys
from dataclasses import dataclass, field

# --------------------------------------------------------------------------- #
# ctypes structures
# --------------------------------------------------------------------------- #

AC_OFF, AC_REPLAY, AC_LIVE, AC_PAUSE = 0, 1, 2, 3


class SPageFilePhysics(ctypes.Structure):
    _pack_ = 4
    _fields_ = [
        ("packetId", ctypes.c_int),
        ("gas", ctypes.c_float),
        ("brake", ctypes.c_float),
        ("fuel", ctypes.c_float),
        ("gear", ctypes.c_int),
        ("rpms", ctypes.c_int),
        ("steerAngle", ctypes.c_float),
        ("speedKmh", ctypes.c_float),
        ("velocity", ctypes.c_float * 3),
        ("accG", ctypes.c_float * 3),
        ("wheelSlip", ctypes.c_float * 4),
        ("wheelLoad", ctypes.c_float * 4),
        ("wheelsPressure", ctypes.c_float * 4),
        ("wheelAngularSpeed", ctypes.c_float * 4),
        ("tyreWear", ctypes.c_float * 4),
        ("tyreDirtyLevel", ctypes.c_float * 4),
        ("tyreCoreTemperature", ctypes.c_float * 4),
        ("camberRAD", ctypes.c_float * 4),
        ("suspensionTravel", ctypes.c_float * 4),
        ("drs", ctypes.c_float),
        ("tc", ctypes.c_float),
        ("heading", ctypes.c_float),
        ("pitch", ctypes.c_float),
        ("roll", ctypes.c_float),
        ("cgHeight", ctypes.c_float),
        ("carDamage", ctypes.c_float * 5),
        ("numberOfTyresOut", ctypes.c_int),
        ("pitLimiterOn", ctypes.c_int),
        ("abs", ctypes.c_float),
        ("kersCharge", ctypes.c_float),
        ("kersInput", ctypes.c_float),
        ("autoShifterOn", ctypes.c_int),
        ("rideHeight", ctypes.c_float * 2),
        ("turboBoost", ctypes.c_float),
        ("ballast", ctypes.c_float),
        ("airDensity", ctypes.c_float),
        ("airTemp", ctypes.c_float),
        ("roadTemp", ctypes.c_float),
        ("localAngularVel", ctypes.c_float * 3),
        ("finalFF", ctypes.c_float),
        ("performanceMeter", ctypes.c_float),
        ("engineBrake", ctypes.c_int),
        ("ersRecoveryLevel", ctypes.c_int),
        ("ersPowerLevel", ctypes.c_int),
        ("ersHeatCharging", ctypes.c_int),
        ("ersIsCharging", ctypes.c_int),
        ("kersCurrentKJ", ctypes.c_float),
        ("drsAvailable", ctypes.c_int),
        ("drsEnabled", ctypes.c_int),
        ("brakeTemp", ctypes.c_float * 4),
        ("clutch", ctypes.c_float),
        ("tyreTempI", ctypes.c_float * 4),
        ("tyreTempM", ctypes.c_float * 4),
        ("tyreTempO", ctypes.c_float * 4),
        ("isAIControlled", ctypes.c_int),
        ("tyreContactPoint", (ctypes.c_float * 3) * 4),
        ("tyreContactNormal", (ctypes.c_float * 3) * 4),
        ("tyreContactHeading", (ctypes.c_float * 3) * 4),
        ("brakeBias", ctypes.c_float),
        ("localVelocity", ctypes.c_float * 3),
    ]


class SPageFileGraphics(ctypes.Structure):
    _pack_ = 4
    _fields_ = [
        ("packetId", ctypes.c_int),
        ("status", ctypes.c_int),
        ("session", ctypes.c_int),
        ("currentTime", ctypes.c_wchar * 15),
        ("lastTime", ctypes.c_wchar * 15),
        ("bestTime", ctypes.c_wchar * 15),
        ("split", ctypes.c_wchar * 15),
        ("completedLaps", ctypes.c_int),
        ("position", ctypes.c_int),
        ("iCurrentTime", ctypes.c_int),
        ("iLastTime", ctypes.c_int),
        ("iBestTime", ctypes.c_int),
        ("sessionTimeLeft", ctypes.c_float),
        ("distanceTraveled", ctypes.c_float),
        ("isInPit", ctypes.c_int),
        ("currentSectorIndex", ctypes.c_int),
        ("lastSectorTime", ctypes.c_int),
        ("numberOfLaps", ctypes.c_int),
        ("tyreCompound", ctypes.c_wchar * 33),
        ("replayTimeMultiplier", ctypes.c_float),
        ("normalizedCarPosition", ctypes.c_float),
        ("carCoordinates", ctypes.c_float * 3),
        ("penaltyTime", ctypes.c_float),
        ("flag", ctypes.c_int),
        ("idealLineOn", ctypes.c_int),
        ("isInPitLane", ctypes.c_int),
        ("surfaceGrip", ctypes.c_float),
        ("mandatoryPitDone", ctypes.c_int),
        ("windSpeed", ctypes.c_float),
        ("windDirection", ctypes.c_float),
    ]


class SPageFileStatic(ctypes.Structure):
    _pack_ = 4
    _fields_ = [
        ("smVersion", ctypes.c_wchar * 15),
        ("acVersion", ctypes.c_wchar * 15),
        ("numberOfSessions", ctypes.c_int),
        ("numCars", ctypes.c_int),
        ("carModel", ctypes.c_wchar * 33),
        ("track", ctypes.c_wchar * 33),
        ("playerName", ctypes.c_wchar * 33),
        ("playerSurname", ctypes.c_wchar * 33),
        ("playerNick", ctypes.c_wchar * 33),
        ("sectorCount", ctypes.c_int),
        ("maxTorque", ctypes.c_float),
        ("maxPower", ctypes.c_float),
        ("maxRpm", ctypes.c_int),
        ("maxFuel", ctypes.c_float),
        ("suspensionMaxTravel", ctypes.c_float * 4),
        ("tyreRadius", ctypes.c_float * 4),
        ("maxTurboBoost", ctypes.c_float),
        ("deprecated_1", ctypes.c_float),
        ("deprecated_2", ctypes.c_float),
        ("penaltiesEnabled", ctypes.c_int),
        ("aidFuelRate", ctypes.c_float),
        ("aidTireRate", ctypes.c_float),
        ("aidMechanicalDamage", ctypes.c_float),
        ("aidAllowTyreBlankets", ctypes.c_int),
        ("aidStability", ctypes.c_float),
        ("aidAutoClutch", ctypes.c_int),
        ("aidAutoBlip", ctypes.c_int),
        ("hasDRS", ctypes.c_int),
        ("hasERS", ctypes.c_int),
        ("hasKERS", ctypes.c_int),
        ("kersMaxJ", ctypes.c_float),
        ("engineBrakeSettingsCount", ctypes.c_int),
        ("ersPowerControllerCount", ctypes.c_int),
        ("trackSPlineLength", ctypes.c_float),
        ("trackConfiguration", ctypes.c_wchar * 33),
        ("ersMaxJ", ctypes.c_float),
        ("isTimedRace", ctypes.c_int),
        ("hasExtraLap", ctypes.c_int),
        ("carSkin", ctypes.c_wchar * 33),
        ("reversedGridPositions", ctypes.c_int),
        ("PitWindowStart", ctypes.c_int),
        ("PitWindowEnd", ctypes.c_int),
    ]


# --------------------------------------------------------------------------- #
# Plain snapshot handed to the rest of the app
# --------------------------------------------------------------------------- #

TYRE_NAMES = ("FL", "FR", "RL", "RR")


def _four() -> list[float]:
    return [0.0, 0.0, 0.0, 0.0]


@dataclass
class Snapshot:
    """One frame of telemetry, already converted to plain Python values."""

    live: bool = False
    status: int = AC_OFF
    car: str = ""
    track: str = ""
    compound: str = ""
    speed_kmh: float = 0.0
    rpm: int = 0
    max_rpm: int = 0
    gear: int = 0
    fuel: float = 0.0
    max_fuel: float = 0.0
    tyre_core: list[float] = field(default_factory=_four)
    tyre_inner: list[float] = field(default_factory=_four)
    tyre_middle: list[float] = field(default_factory=_four)
    tyre_outer: list[float] = field(default_factory=_four)
    tyre_pressure: list[float] = field(default_factory=_four)
    tyre_wear: list[float] = field(default_factory=_four)
    brake_temp: list[float] = field(default_factory=_four)
    completed_laps: int = 0
    current_time_ms: int = 0
    last_time_ms: int = 0
    best_time_ms: int = 0
    normalized_pos: float = 0.0
    in_pit: bool = False
    air_temp: float = 0.0
    road_temp: float = 0.0


class ACSharedMemory:
    """Opens the three AC pages. Safe to construct before AC is running: the
    pages read as zeros and ``Snapshot.live`` stays False until AC goes live."""

    def __init__(self) -> None:
        if sys.platform != "win32":
            raise RuntimeError("Assetto Corsa shared memory only exists on Windows")
        self._phys_mm = mmap.mmap(-1, ctypes.sizeof(SPageFilePhysics), "Local\\acpmf_physics")
        self._gfx_mm = mmap.mmap(-1, ctypes.sizeof(SPageFileGraphics), "Local\\acpmf_graphics")
        self._stat_mm = mmap.mmap(-1, ctypes.sizeof(SPageFileStatic), "Local\\acpmf_static")
        self._phys = SPageFilePhysics.from_buffer(self._phys_mm)
        self._gfx = SPageFileGraphics.from_buffer(self._gfx_mm)
        self._stat = SPageFileStatic.from_buffer(self._stat_mm)
        self._last_packet = -1
        self._stale_reads = 0

    def read(self) -> Snapshot:
        p, g, s = self._phys, self._gfx, self._stat
        # AC bumps packetId every physics tick. If it stops moving the game is
        # paused, in a menu, or closed, so after ~1 s of no movement we report
        # the snapshot as not live.
        if p.packetId != self._last_packet:
            self._last_packet = p.packetId
            self._stale_reads = 0
        else:
            self._stale_reads += 1
        live = g.status == AC_LIVE and self._stale_reads < 60

        return Snapshot(
            live=live,
            status=g.status,
            car=s.carModel,
            track=s.track,
            compound=g.tyreCompound,
            speed_kmh=p.speedKmh,
            rpm=p.rpms,
            max_rpm=s.maxRpm,
            gear=p.gear - 1,  # AC: 0 = reverse, 1 = neutral, 2 = first
            fuel=p.fuel,
            max_fuel=s.maxFuel,
            tyre_core=list(p.tyreCoreTemperature),
            tyre_inner=list(p.tyreTempI),
            tyre_middle=list(p.tyreTempM),
            tyre_outer=list(p.tyreTempO),
            tyre_pressure=list(p.wheelsPressure),
            tyre_wear=list(p.tyreWear),
            brake_temp=list(p.brakeTemp),
            completed_laps=g.completedLaps,
            current_time_ms=g.iCurrentTime,
            last_time_ms=g.iLastTime,
            best_time_ms=g.iBestTime,
            normalized_pos=g.normalizedCarPosition,
            in_pit=bool(g.isInPit or g.isInPitLane),
            air_temp=p.airTemp,
            road_temp=p.roadTemp,
        )

    def close(self) -> None:
        # ctypes views must be released before the mmap can close.
        del self._phys, self._gfx, self._stat
        for m in (self._phys_mm, self._gfx_mm, self._stat_mm):
            m.close()
