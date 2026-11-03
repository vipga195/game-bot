import random

import pytest

from gamebot.db import connect, init_db
from gamebot.play import Player, PlayerConfig, Recorder, ScreenChanged, StepFailed
from gamebot.script import AssetStore, Point
from gamebot.script.repo import ScriptRepo

from .fakes import two_screen_game


def test_point_roundtrip_and_edge_anchor():
    p = Point.from_px(180, 320, 360, 640, 160)
    assert p.to_px(360, 640, 160) == (180, 320)
    assert p.to_px(720, 1280, 320) == (360, 640)
    r = Point.from_px(340, 20, 360, 640, 160, "r", "t")  # 20dp from right edge
    assert r.to_px(720, 1280, 320) == (680, 40)  # still 20dp (40px) from the right edge


def record(tmp_path):
    dev = two_screen_game()
    rec = Recorder(dev, AssetStore(tmp_path, "s1"), "s1", "g1", sleep=lambda s: None)
    rec.mark_screen("login", (100 / 360, 20 / 640, 260 / 360, 80 / 640))
    rec.record_tap(180, 325, from_screen="login")
    rec.mark_screen("main", (100 / 360, 20 / 640, 260 / 360, 80 / 640))
    rec.script.steps[0].to_screen = "main"
    return rec.finish(), dev


def test_record_and_play(tmp_path):
    script, dev = record(tmp_path)
    assert script.steps[0].template and script.ref_width == 360
    dev.cur = "login"
    dev.taps.clear()
    Player(dev, script, AssetStore(tmp_path, "s1"), sleep=lambda s: None).run()
    assert dev.cur == "main" and len(dev.taps) == 1


def test_script_repo_roundtrip(tmp_path):
    script, _ = record(tmp_path)
    conn = connect(":memory:")
    init_db(conn)
    repo = ScriptRepo(conn)
    repo.save(script)
    repo.save(script)
    assert repo.load("s1") == script
    assert conn.execute("SELECT version FROM scripts").fetchone()[0] == 2
    assert repo.for_game("g1", "task").id == "s1"


def test_forces_and_restores_size(tmp_path):
    script, dev = record(tmp_path)
    dev.cur = "login"
    seen = []
    orig = dev.set_screen
    dev.set_screen = lambda *a: (seen.append(a), orig(*a))
    dev.info = type(dev.info)(720, 1280, 320)  # emulator currently differs
    dev.physical = dev.info
    # screens are rendered at ref size once forced, so the replay still works
    Player(dev, script, AssetStore(tmp_path, "s1"), sleep=lambda s: None).run()
    assert seen == [(360, 640, 160)] and not dev.overridden and dev.info.width == 720


def test_stops_when_size_changes_midway(tmp_path):
    script, dev = record(tmp_path)
    dev.cur = "login"

    def change(d):
        d.info = type(d.info)(500, 900, 240)

    p = Player(dev, script, AssetStore(tmp_path, "s1"), sleep=lambda s: None)
    orig = dev.tap
    dev.tap = lambda x, y: (orig(x, y), change(dev))
    with pytest.raises(ScreenChanged):
        p.run()


def test_step_fails_with_screenshot(tmp_path):
    script, dev = record(tmp_path)
    dev.cur = "main"  # wrong screen, no handlers
    p = Player(
        dev,
        script,
        AssetStore(tmp_path, "s1"),
        PlayerConfig(screen_timeout=0.0),
        sleep=lambda s: None,
    )
    with pytest.raises(StepFailed) as e:
        p.run()
    assert e.value.screenshot


def test_jitter_is_bounded(tmp_path):
    script, dev = record(tmp_path)
    dev.cur = "login"
    dev.taps.clear()
    Player(
        dev,
        script,
        AssetStore(tmp_path, "s1"),
        PlayerConfig(jitter_px=3),
        sleep=lambda s: None,
        rng=random.Random(1),
    ).run()
    x, y = dev.taps[0]
    assert abs(x - 180) <= 4 and abs(y - 325) <= 4


def test_letterbox_when_size_cannot_be_forced(tmp_path):
    import cv2

    script, _ = record(tmp_path)
    big = two_screen_game()
    big.screens = {k: cv2.resize(v, None, fx=2, fy=2) for k, v in big.screens.items()}
    big.buttons = {"login": (240, 600, 240, 100, 21, "main")}
    big.info = big.physical = type(big.info)(720, 1280, 320)
    big.set_screen = lambda *a: None  # emulator refuses to resize
    Player(big, script, AssetStore(tmp_path, "s1"), sleep=lambda s: None).run()
    assert big.cur == "main"
