"""Telemetry loop: read AC -> classify tyres -> paint LEDs -> broadcast JSON."""
from __future__ import annotations

import asyncio
import functools
import http.server
import json
import logging
import threading
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any

from websockets.asyncio.server import ServerConnection, broadcast, serve

from . import moza, tyres
from .ac_shared_memory import TYRE_NAMES, Snapshot
from .delta import DeltaTracker
from .fuel import FuelTracker

log = logging.getLogger(__name__)
OVERLAY_DIR = Path(__file__).resolve().parent.parent / "overlay"


class TelemetryServer:
    def __init__(
        self,
        source: Any,
        wheel: moza.MozaWheel | None,
        led_count: int = 10,
        windows: dict[str, tyres.TempWindow] | None = None,
        ws_port: int = 8765,
        http_port: int = 8000,
        hz: float = 20.0,
        fuel_warning_laps: float = 2.0,
    ) -> None:
        self.source = source
        self.wheel = wheel
        self.led_count = led_count
        self.windows = windows
        self.ws_port = ws_port
        self.http_port = http_port
        self.period = 1.0 / hz
        self.fuel_warning_laps = fuel_warning_laps
        self.delta = DeltaTracker()
        self.fuel = FuelTracker()
        self.clients: set[ServerConnection] = set()
        self.last_message: str = "{}"
        self._blink_phase = True
        self._led_error_logged = False

    # -- one telemetry tick ---------------------------------------------------

    def tick(self) -> dict:
        s: Snapshot = self.source.read()
        state = tyres.assess(s, self.windows)
        self.delta.update(s)
        self.fuel.update(s)

        fuel_warning = self.fuel.laps_left is not None and self.fuel.laps_left < self.fuel_warning_laps
        self._blink_phase = int(time.monotonic() * 4) % 2 == 0  # 2 Hz blink
        colours = tyres.led_colours(state, self.led_count, fuel_warning)
        lit = tyres.led_lit(state, self.led_count, self._blink_phase)
        if not s.live:
            colours = [(0, 0, 0)] * self.led_count
            lit = [False] * self.led_count
        self._drive_leds(state, colours, lit, s.live)

        return {
            "live": s.live,
            "status": s.status,
            "car": s.car,
            "track": s.track,
            "compound": s.compound,
            "speedKmh": round(s.speed_kmh, 1),
            "rpm": s.rpm,
            "maxRpm": s.max_rpm,
            "gear": s.gear,
            "airTemp": round(s.air_temp, 1),
            "roadTemp": round(s.road_temp, 1),
            "fuel": {
                "litres": round(s.fuel, 2),
                "maxLitres": round(s.max_fuel, 1),
                "perLap": None if self.fuel.per_lap is None else round(self.fuel.per_lap, 2),
                "lapsLeft": None if self.fuel.laps_left is None else round(self.fuel.laps_left, 1),
                "warning": fuel_warning,
            },
            "tyres": [
                {
                    "name": TYRE_NAMES[i],
                    "core": round(s.tyre_core[i], 1),
                    "inner": round(s.tyre_inner[i], 1),
                    "middle": round(s.tyre_middle[i], 1),
                    "outer": round(s.tyre_outer[i], 1),
                    "pressure": round(s.tyre_pressure[i], 1),
                    "wear": round(s.tyre_wear[i], 1),
                    "brake": round(s.brake_temp[i], 0),
                    "condition": state.conditions[i].value,
                }
                for i in range(4)
            ],
            "window": asdict(state.window),
            "delta": {
                "ms": None if self.delta.delta_ms is None else round(self.delta.delta_ms),
                "refLapMs": self.delta.reference_lap_ms,
            },
            "lap": {
                "completed": s.completed_laps,
                "currentMs": s.current_time_ms,
                "lastMs": s.last_time_ms,
                "bestMs": s.best_time_ms,
            },
            "leds": {"count": self.led_count, "colours": colours, "lit": lit, "layout": tyres.led_layout(self.led_count)},
            "wheel": {
                "connected": self.wheel is not None,
                "port": getattr(self.wheel, "port_name", None),
                "legacy": isinstance(self.wheel, moza.LegacyMozaWheel),
            },
        }

    def _drive_leds(self, state: tyres.TyreState, colours, lit, live: bool) -> None:
        if self.wheel is None:
            return
        try:
            if isinstance(self.wheel, moza.LegacyMozaWheel):
                self.wheel.show_severity(state.severity if live else 0.0)
            else:
                self.wheel.show(colours, lit)
            self._led_error_logged = False
        except Exception as exc:  # serial hiccup: keep the overlay alive
            if not self._led_error_logged:
                log.warning("LED write failed (%s); will keep trying", exc)
                self._led_error_logged = True

    # -- servers --------------------------------------------------------------

    async def _ws_handler(self, ws: ServerConnection) -> None:
        self.clients.add(ws)
        try:
            await ws.send(self.last_message)
            async for _ in ws:  # we ignore inbound messages; keep the socket open
                pass
        finally:
            self.clients.discard(ws)

    async def _loop(self) -> None:
        next_tick = time.monotonic()
        while True:
            try:
                payload = self.tick()
                self.last_message = json.dumps(payload)
                broadcast(self.clients, self.last_message)
            except Exception:
                log.exception("telemetry tick failed")
            next_tick += self.period
            await asyncio.sleep(max(0.0, next_tick - time.monotonic()))

    def _start_http(self) -> None:
        class QuietHandler(http.server.SimpleHTTPRequestHandler):
            def log_message(self, *args) -> None:  # keep the console for telemetry
                pass

        handler = functools.partial(QuietHandler, directory=str(OVERLAY_DIR))
        httpd = http.server.ThreadingHTTPServer(("127.0.0.1", self.http_port), handler)
        threading.Thread(target=httpd.serve_forever, daemon=True, name="overlay-http").start()
        log.info("Overlay:   http://127.0.0.1:%d/", self.http_port)

    async def run(self) -> None:
        self._start_http()
        async with serve(self._ws_handler, "127.0.0.1", self.ws_port):
            log.info("WebSocket: ws://127.0.0.1:%d/", self.ws_port)
            await self._loop()
