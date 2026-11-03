from __future__ import annotations

from gamebot.play import GeteventParser, LiveRecorder, Recorder
from gamebot.script import AssetStore

from .fakes import two_screen_game

PROPS = """add device 1: /dev/input/event2
  name:     "Power Button"
  events:
    KEY (0001): KEY_POWER
add device 2: /dev/input/event4
  name:     "virtio_input_multi_touch_1"
  events:
    ABS (0003): ABS_MT_SLOT           : value 0, min 0, max 9, fuzz 0, flat 0, resolution 0
                ABS_MT_TRACKING_ID    : value 0, min 0, max 65535, fuzz 0, flat 0, resolution 0
                ABS_MT_POSITION_X     : value 0, min 0, max 3599, fuzz 0, flat 0, resolution 0
                ABS_MT_POSITION_Y     : value 0, min 0, max 6399, fuzz 0, flat 0, resolution 0
"""

D = "/dev/input/event4"


def ev(t, typ, code, val, dev=D):
    return f"[{t:>15.6f}] {dev}: {typ:<12} {code:<20} {val}"


def tap_lines(t, x, y):
    return [
        ev(t, "EV_ABS", "ABS_MT_TRACKING_ID", "00000011"),
        ev(t, "EV_ABS", "ABS_MT_POSITION_X", f"{x:08x}"),
        ev(t, "EV_ABS", "ABS_MT_POSITION_Y", f"{y:08x}"),
        ev(t, "EV_KEY", "BTN_TOUCH", "DOWN"),
        ev(t, "EV_SYN", "SYN_REPORT", "00000000"),
        ev(t + 0.08, "EV_ABS", "ABS_MT_TRACKING_ID", "ffffffff"),
        ev(t + 0.08, "EV_KEY", "BTN_TOUCH", "UP"),
        ev(t + 0.08, "EV_SYN", "SYN_REPORT", "00000000"),
    ]


def swipe_lines(t):
    out = tap_lines(t, 1800, 4800)[:5]
    out += [
        ev(t + 0.1, "EV_ABS", "ABS_MT_POSITION_Y", f"{1600:08x}"),
        ev(t + 0.1, "EV_SYN", "SYN_REPORT", "00000000"),
        ev(t + 0.3, "EV_ABS", "ABS_MT_TRACKING_ID", "ffffffff"),
        ev(t + 0.3, "EV_SYN", "SYN_REPORT", "00000000"),
    ]
    return out


def parser(**kw):
    return GeteventParser({"X": (0, 3599), "Y": (0, 6399)}, 360, 640, D, **kw)


def run(p, lines):
    return [g for ln in lines if (g := p.feed(ln))]


def test_tap_scaled_to_screen_pixels():
    (g,) = run(parser(), tap_lines(100.0, 1800, 3200))
    assert (g.kind, g.x1, g.y1) == ("tap", 180, 320) and 70 <= g.ms <= 90


def test_swipe_with_duration():
    (g,) = run(parser(), swipe_lines(50.0))
    assert g.kind == "swipe" and (g.x1, g.y1) == (180, 479) and (g.x2, g.y2) == (180, 160)
    assert 290 <= g.ms <= 310


def test_ignores_other_devices_second_finger_and_noise():
    p = parser()
    other = [ev(1.0, "EV_KEY", "KEY_POWER", "DOWN", dev="/dev/input/event2"), "garbage line"]
    second = [ev(2.0, "EV_ABS", "ABS_MT_SLOT", "00000001"), *tap_lines(2.0, 100, 100)[:5]]
    assert run(p, other + second) == []


def test_on_down_fires_before_gesture():
    seen = []
    p = parser(on_down=lambda x, y: seen.append((x, y)))
    lines = tap_lines(1.0, 900, 1600)
    assert run(p, lines[:5]) == [] and seen == [(90, 160)]


def test_live_recorder_records_steps_without_executing(tmp_path):
    dev = two_screen_game()
    rec = Recorder(dev, AssetStore(tmp_path, "s1"), "s1", "g1", sleep=lambda s: None)
    lines = [*tap_lines(10.0, 1800, 3200), *swipe_lines(20.0)]
    LiveRecorder(rec, lines, PROPS).run()
    steps = rec.finish().steps
    assert [s.action for s in steps] == ["tap", "swipe"]
    assert steps[0].template and dev.taps == []
