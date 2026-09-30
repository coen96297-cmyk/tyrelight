"""MOZA wheel LED driver over the wheelbase's USB serial port.

Wire format (reverse engineered by the boxflat project and cross-checked
byte-for-byte by moza-rev; see README "Credits"):

    7E  N  GROUP  DEVICE  CMD...  PAYLOAD...  CHK

* ``N``     = len(CMD) + len(PAYLOAD)
* ``CHK``   = (0x0D + sum of every preceding byte) & 0xFF
* Any 0x7E byte from GROUP onwards is doubled on the wire (byte stuffing) and
  both copies count toward the checksum. The checksum byte itself is doubled
  too if it happens to be 0x7E.

Three wheel commands (group 0x3F = "wheel write", device 0x17 = wheel) give us
everything needed to paint arbitrary colours on the RPM LED bar:

* ``telemetry-mode``      cmd [0x1C, 0x00], 1 byte   -> 1 = LEDs follow telemetry
* ``telemetry-rpm-colors`` cmd [0x19, 0x00], 20 bytes -> five [index, R, G, B]
  entries per frame, so ten LEDs take two frames
* ``send-rpm-telemetry``   cmd [0x1A, 0x00], 2 bytes  -> little-endian bitmask
  of which LEDs are lit

Legacy ES wheels bundled with R3/R5 bases can only take an RPM *value*, not
per-LED colours; they are handled by ``LegacyMozaWheel`` which lights the bar
proportionally to how bad the worst tyre is.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Iterable, Sequence

log = logging.getLogger(__name__)

MESSAGE_START = 0x7E
CHECKSUM_MAGIC = 0x0D
BAUD_RATE = 115200
MOZA_USB_VID = 0x346E  # Gudsen Technology (MOZA Racing)

GROUP_WHEEL_WRITE = 0x3F
GROUP_BASE_SETTING_WRITE = 0x40
GROUP_BASE_TELEMETRY = 0x41
DEVICE_WHEEL = 0x17
DEVICE_BASE = 0x13

CMD_TELEMETRY_MODE = (0x1C, 0x00)
CMD_TELEMETRY_RPM_COLORS = (0x19, 0x00)
CMD_SEND_RPM_TELEMETRY = (0x1A, 0x00)
CMD_LEGACY_INDICATOR_MODE = (0x04,)
CMD_LEGACY_SEND_TELEMETRY = (0xFD, 0xDE)

RGB = tuple[int, int, int]


# --------------------------------------------------------------------------- #
# Frame building (pure functions, unit-tested)
# --------------------------------------------------------------------------- #

def checksum(frame: Sequence[int]) -> int:
    total = CHECKSUM_MAGIC + sum(frame)
    total += sum(MESSAGE_START for b in frame[2:] if b == MESSAGE_START)
    return total & 0xFF


def build_frame(group: int, device: int, cmd: Sequence[int], payload: Sequence[int]) -> bytes:
    body = [MESSAGE_START, len(cmd) + len(payload), group, device, *cmd, *payload]
    body.append(checksum(body))
    return bytes(body)


def byte_stuff(frame: bytes) -> bytes:
    out = bytearray(frame[:2])
    for b in frame[2:]:
        out.append(b)
        if b == MESSAGE_START:
            out.append(MESSAGE_START)
    return bytes(out)


def telemetry_mode_frame(enabled: bool = True) -> bytes:
    return build_frame(GROUP_WHEEL_WRITE, DEVICE_WHEEL, CMD_TELEMETRY_MODE, [1 if enabled else 0])


def led_colour_frames(colours: Sequence[RGB]) -> list[bytes]:
    """Five ``[index, r, g, b]`` entries per 20-byte frame."""
    frames = []
    for start in range(0, len(colours), 5):
        chunk = colours[start:start + 5]
        payload: list[int] = []
        for offset, (r, g, b) in enumerate(chunk):
            payload += [start + offset, r & 0xFF, g & 0xFF, b & 0xFF]
        payload += [0] * (20 - len(payload))
        frames.append(build_frame(GROUP_WHEEL_WRITE, DEVICE_WHEEL, CMD_TELEMETRY_RPM_COLORS, payload))
    return frames


def led_bitmask_frame(bitmask: int, led_count: int = 10) -> bytes:
    if led_count > 16:
        payload = list(bitmask.to_bytes(4, "little"))
    else:
        payload = list((bitmask & 0xFFFF).to_bytes(2, "little"))
    return build_frame(GROUP_WHEEL_WRITE, DEVICE_WHEEL, CMD_SEND_RPM_TELEMETRY, payload)


def legacy_rpm_frame(value: int) -> bytes:
    """ES wheels: 0..1023 'RPM percent', big-endian, addressed to the BASE."""
    return build_frame(GROUP_BASE_TELEMETRY, DEVICE_BASE, CMD_LEGACY_SEND_TELEMETRY,
                       list(max(0, min(1023, value)).to_bytes(4, "big")))


def legacy_indicator_mode_frame(mode: int = 1) -> bytes:
    """1 = telemetry driven, 2 = off, 3 = always on."""
    return build_frame(GROUP_BASE_SETTING_WRITE, DEVICE_BASE, CMD_LEGACY_INDICATOR_MODE, [mode])


# --------------------------------------------------------------------------- #
# Serial port discovery
# --------------------------------------------------------------------------- #

@dataclass
class PortInfo:
    device: str
    description: str
    legacy: bool


def find_moza_ports() -> list[PortInfo]:
    """Return every serial port that looks like a MOZA base, base first."""
    from serial.tools import list_ports  # imported lazily so tests run without pyserial

    found: list[PortInfo] = []
    for p in list_ports.comports():
        text = " ".join(filter(None, [p.description, p.manufacturer, p.product, p.hwid])).lower()
        if p.vid == MOZA_USB_VID or "moza" in text or "gudsen" in text:
            legacy = any(tag in text for tag in ("_r5_", " r5 ", "_r3_", " r3 ", "r5 base", "r3 base"))
            found.append(PortInfo(p.device, p.description or "", legacy))
    found.sort(key=lambda i: ("base" not in i.description.lower(), i.device))
    return found


# --------------------------------------------------------------------------- #
# Drivers
# --------------------------------------------------------------------------- #

class MozaWheel:
    """Per-LED colour control for modern MOZA wheels (CS, KS, FSR, GS, ES-on-R9+...)."""

    def __init__(self, port: str, led_count: int = 10, write_hz: float = 20.0) -> None:
        import serial

        self.port_name = port
        self.led_count = led_count
        self._min_interval = 1.0 / write_hz
        self._last_colours: list[RGB] | None = None
        self._last_mask: int | None = None
        self._last_write = 0.0
        self._serial = serial.Serial(port, BAUD_RATE, timeout=0.2, write_timeout=0.5, exclusive=False)
        self._serial.reset_input_buffer()
        self._write(telemetry_mode_frame(True))
        log.info("MOZA wheel on %s, %d LEDs, telemetry mode on", port, led_count)

    # -- public API ---------------------------------------------------------

    def show(self, colours: Sequence[RGB], lit: Iterable[bool] | None = None) -> None:
        """Paint ``colours`` onto the bar. ``lit`` masks individual LEDs off
        (used for blinking); unlit LEDs keep their colour but stay dark."""
        colours = list(colours)[: self.led_count]
        colours += [(0, 0, 0)] * (self.led_count - len(colours))
        mask = 0
        lit_flags = list(lit) if lit is not None else [True] * self.led_count
        for i, (rgb, on) in enumerate(zip(colours, lit_flags)):
            if on and rgb != (0, 0, 0):
                mask |= 1 << i

        colours_changed = colours != self._last_colours
        mask_changed = mask != self._last_mask
        keepalive = time.monotonic() - self._last_write > 1.0
        if not (colours_changed or mask_changed or keepalive):
            return

        # Don't spam the serial link faster than write_hz for pure mask changes.
        if not colours_changed and not keepalive and time.monotonic() - self._last_write < self._min_interval:
            return

        if colours_changed:
            for frame in led_colour_frames(colours):
                self._write(frame)
            self._last_colours = colours
        self._write(led_bitmask_frame(mask, self.led_count))
        self._last_mask = mask
        self._last_write = time.monotonic()

    def clear(self) -> None:
        self._write(led_bitmask_frame(0, self.led_count))
        self._last_mask = 0

    def close(self) -> None:
        try:
            self.clear()
            # Hand the bar back to Pit House's own RPM logic.
            self._write(telemetry_mode_frame(False))
        finally:
            self._serial.close()

    # -- internals ----------------------------------------------------------

    def _write(self, frame: bytes) -> None:
        wire = byte_stuff(frame)
        log.debug("-> %s", wire.hex(" "))
        self._serial.write(wire)
        self._serial.flush()


class LegacyMozaWheel(MozaWheel):
    """R3/R5 + bundled ES wheel. Colours are fixed by Pit House, so we can
    only choose *how many* LEDs light. We fill the bar with the worst tyre's
    severity: 0 = all ideal, full bar = something is overheated."""

    def __init__(self, port: str, led_count: int = 10, write_hz: float = 20.0) -> None:
        import serial

        self.port_name = port
        self.led_count = led_count
        self._min_interval = 1.0 / write_hz
        self._last_value: int | None = None
        self._last_write = 0.0
        self._serial = serial.Serial(port, BAUD_RATE, timeout=0.2, write_timeout=0.5, exclusive=False)
        self._write(legacy_indicator_mode_frame(1))
        log.info("Legacy MOZA (ES) wheel on %s", port)

    def show_severity(self, severity: float) -> None:
        value = int(max(0.0, min(1.0, severity)) * 1023)
        now = time.monotonic()
        if value == self._last_value and now - self._last_write < 1.0:
            return
        if now - self._last_write < self._min_interval and value == self._last_value:
            return
        self._write(legacy_rpm_frame(value))
        self._last_value = value
        self._last_write = now

    def show(self, colours: Sequence[RGB], lit: Iterable[bool] | None = None) -> None:  # noqa: D401
        raise NotImplementedError("Legacy ES wheels cannot take per-LED colours; use show_severity()")

    def clear(self) -> None:
        self._write(legacy_rpm_frame(0))

    def close(self) -> None:
        try:
            self.clear()
        finally:
            self._serial.close()


def open_wheel(port: str | None = None, led_count: int = 10, legacy: bool | None = None) -> MozaWheel:
    """Open the first MOZA base found (or ``port``). Raises RuntimeError if none."""
    if port is None:
        ports = find_moza_ports()
        if not ports:
            raise RuntimeError(
                "No MOZA base found. Is it plugged in and powered? "
                "Pass --port COMx to choose a port manually."
            )
        info = ports[0]
        port = info.device
        if legacy is None:
            legacy = info.legacy
    cls = LegacyMozaWheel if legacy else MozaWheel
    return cls(port, led_count)
