"""Frame builders checked against byte sequences captured from Pit House /
boxflat by the moza-rev project (its unit tests carry the same vectors)."""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from tyrelight import moza, tyres  # noqa: E402
from tyrelight.ac_shared_memory import Snapshot  # noqa: E402


def test_modern_bitmask_none_lit():
    assert moza.led_bitmask_frame(0, 10) == bytes([0x7E, 0x04, 0x3F, 0x17, 0x1A, 0x00, 0x00, 0x00, 0xFF])


def test_modern_bitmask_all_ten_lit():
    assert moza.led_bitmask_frame(0x3FF, 10) == bytes([0x7E, 0x04, 0x3F, 0x17, 0x1A, 0x00, 0xFF, 0x03, 0x01])


def test_modern_bitmask_18_leds_uses_four_bytes():
    frame = moza.led_bitmask_frame(0x3FFFF, 18)
    assert frame[:6] == bytes([0x7E, 0x06, 0x3F, 0x17, 0x1A, 0x00])
    assert len(frame) == 11


def test_legacy_rpm_full():
    assert moza.legacy_rpm_frame(0x3FF) == bytes([0x7E, 0x06, 0x41, 0x13, 0xFD, 0xDE, 0x00, 0x00, 0x03, 0xFF, 0xC2])


def test_colour_frames_two_chunks_of_five():
    colours = [(i, 2 * i, 3 * i) for i in range(10)]
    frames = moza.led_colour_frames(colours)
    assert len(frames) == 2
    for frame in frames:
        assert frame[1] == 22  # 2 cmd bytes + 20 payload bytes
        assert frame[2:6] == bytes([0x3F, 0x17, 0x19, 0x00])
    assert frames[0][6:10] == bytes([0, 0, 0, 0])
    assert frames[1][6:10] == bytes([5, 5, 10, 15])


def test_byte_stuffing_doubles_7e_in_body_and_checksum():
    frame = moza.build_frame(0x3F, 0x17, (0x19, 0x00), [0x7E, 0x00])
    wire = moza.byte_stuff(frame)
    assert wire.count(0x7E) >= 3  # start byte + doubled payload byte
    assert wire[:2] == frame[:2]  # start + length never stuffed


def test_tyre_classification_and_layout():
    snap = Snapshot(live=True, compound="Slick (M)", tyre_core=[60, 90, 108, 120])
    state = tyres.assess(snap)
    assert [c.value for c in state.conditions] == ["cold", "ideal", "hot", "overheated"]
    assert state.severity == 1.0
    layout = tyres.led_layout(10)
    assert layout == [0, 0, 2, 2, None, None, 3, 3, 1, 1]
    colours = tyres.led_colours(state, 10)
    assert colours[0] == tyres.LED_COLOURS[tyres.Condition.COLD]
    assert colours[-1] == tyres.LED_COLOURS[tyres.Condition.IDEAL]
    lit = tyres.led_lit(state, 10, blink_phase=False)
    assert lit == [True, True, True, True, True, True, False, False, True, True]


def test_window_matching_prefers_exact_then_family():
    custom = {"Soft (S)": tyres.TempWindow(1, 2, 3), "slick": tyres.TempWindow(4, 5, 6)}
    assert tyres.window_for("Soft (S)", custom).cold_below == 1
    assert tyres.window_for("Hard (H) slick", custom).cold_below == 4
    assert tyres.window_for("Whatever", custom) is tyres.DEFAULT_WINDOWS["default"]
