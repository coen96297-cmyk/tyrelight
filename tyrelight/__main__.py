"""CLI entry point: ``python -m tyrelight [--demo] [--port COM5] [--leds 10]``."""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path

from . import moza, tyres
from .server import TelemetryServer


def load_windows(path: Path | None) -> dict[str, tyres.TempWindow] | None:
    if path is None:
        return None
    data = json.loads(path.read_text())
    return {
        name: tyres.TempWindow(**{k: float(v) for k, v in spec.items()})
        for name, spec in data.get("compounds", {}).items()
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="tyrelight", description="Assetto Corsa telemetry overlay + MOZA tyre-condition LEDs")
    ap.add_argument("--demo", action="store_true", help="synthetic telemetry instead of Assetto Corsa")
    ap.add_argument("--demo-speed", type=float, default=1.0, help="time multiplier for --demo")
    ap.add_argument("--port", help="serial port of the MOZA base (auto-detected if omitted)")
    ap.add_argument("--leds", type=int, default=10, help="number of RPM LEDs on the wheel (default 10)")
    ap.add_argument("--legacy", action="store_true", help="force the R3/R5 ES-wheel protocol")
    ap.add_argument("--no-leds", action="store_true", help="overlay only, do not touch the wheel")
    ap.add_argument("--config", type=Path, default=None, help="JSON with per-compound temperature windows")
    ap.add_argument("--ws-port", type=int, default=8765)
    ap.add_argument("--http-port", type=int, default=8000)
    ap.add_argument("--hz", type=float, default=20.0, help="telemetry rate")
    ap.add_argument("-v", "--verbose", action="store_true", help="log every serial frame")
    args = ap.parse_args(argv)

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="%(levelname)s %(message)s")
    log = logging.getLogger("tyrelight")

    if args.demo:
        from .demo import DemoSource

        source = DemoSource(speed=args.demo_speed)
        log.info("Demo telemetry (no Assetto Corsa needed)")
    else:
        from .ac_shared_memory import ACSharedMemory

        source = ACSharedMemory()
        log.info("Reading Assetto Corsa shared memory; waiting for a live session")

    wheel = None
    if not args.no_leds:
        try:
            wheel = moza.open_wheel(args.port, args.leds, legacy=True if args.legacy else None)
        except Exception as exc:
            log.warning("MOZA wheel not available (%s). Running overlay only. Tip: close Pit House first.", exc)

    default_config = Path(__file__).resolve().parent.parent / "config.json"
    config_path = args.config or (default_config if default_config.exists() else None)
    windows = load_windows(config_path)
    if config_path:
        log.info("Temperature windows from %s", config_path)

    server = TelemetryServer(
        source, wheel, led_count=args.leds, windows=windows,
        ws_port=args.ws_port, http_port=args.http_port, hz=args.hz,
    )
    try:
        asyncio.run(server.run())
    except KeyboardInterrupt:
        pass
    finally:
        if wheel is not None:
            wheel.close()
        source.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
