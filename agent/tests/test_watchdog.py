from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from gamebot.core.runner import RowRunner, RunResult
from gamebot.core.scheduler import Scheduler
from gamebot.play import GameLost, Player, PlayerConfig, ScreenFrozen
from gamebot.script import AssetStore

from .fakes import H, W, noise
from .test_m2 import record


class FakeClock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


def make_player(tmp_path, dev, clk, **cfg):
    script, _ = record(tmp_path)
    return Player(
        dev,
        script,
        AssetStore(tmp_path, "s1"),
        PlayerConfig(**cfg),
        sleep=lambda s: None,
        clock=clk,
    )


def raise_game_lost(*a):
    raise GameLost("game not in foreground: com.other")


def test_game_lost_when_other_app_in_foreground(tmp_path):
    dev = record(tmp_path)[1]
    dev.cur = "login"
    clk = FakeClock()
    dev.foreground_package = lambda: "com.other"
    p = make_player(
        tmp_path, dev, clk, watch_package="com.game", fg_check_s=0.0, still_s=0.0, fg_misses=1
    )
    with pytest.raises(GameLost):
        p.grab()


def test_unknown_foreground_is_ignored(tmp_path):
    dev = record(tmp_path)[1]
    dev.cur = "login"
    clk = FakeClock()
    dev.foreground_package = lambda: None
    p = make_player(tmp_path, dev, clk, watch_package="com.game", fg_check_s=0.0, still_s=0.0)
    p.grab()


def test_fg_check_respects_interval(tmp_path):
    dev = record(tmp_path)[1]
    dev.cur = "login"
    clk = FakeClock()
    dev.foreground_package = lambda: "com.other"
    p = make_player(
        tmp_path, dev, clk, watch_package="com.game", fg_check_s=5.0, still_s=0.0, fg_misses=1
    )
    p.grab()  # last check at t=0, interval not elapsed
    clk.t = 5
    with pytest.raises(GameLost):
        p.grab()


def test_frozen_screen_raises(tmp_path):
    dev = record(tmp_path)[1]
    dev.cur = "login"
    clk = FakeClock()
    p = make_player(tmp_path, dev, clk, still_s=180.0)
    p.grab()
    clk.t = 179
    p.grab()
    clk.t = 180
    with pytest.raises(ScreenFrozen):
        p.grab()


def test_changing_frames_do_not_freeze(tmp_path):
    dev = record(tmp_path)[1]
    dev.cur = "login"
    clk = FakeClock()
    dev.on_screencap = lambda d: d.screens.__setitem__("login", noise(int(clk.t), W, H))
    p = make_player(tmp_path, dev, clk, still_s=180.0)
    for t in (0, 100, 200, 300, 400):
        clk.t = t
        p.grab()


def test_runner_maps_game_lost_to_failed_result(tmp_path):
    dev = record(tmp_path)[1]
    runner = RowRunner.__new__(RowRunner)
    runner.games = SimpleNamespace(get=lambda gid: SimpleNamespace(id=1, package="com.game"))
    runner.scripts = SimpleNamespace(for_game=lambda gid, mode: object())
    runner.device_factory = lambda serial: dev
    runner.ensure_serial = lambda row: "serial"
    runner.sleep = lambda s: None
    runner._play = raise_game_lost
    row = SimpleNamespace(id=1, game_id=1, account_id=None)
    res = runner.run(row, "task")
    assert res.ok is False
    assert res.error.startswith("GameLost")
    assert res.screenshot


def test_scheduler_error_event_carries_screenshot():
    row = SimpleNamespace(id=1, schedule=SimpleNamespace(last_run={}))
    rows = SimpleNamespace(get=lambda rid: row, save=lambda r: None)
    events = []
    sched = Scheduler(
        rows,
        lambda r, m: RunResult(False, "GameLost: x", b"png"),
        lambda: datetime(2026, 1, 1, tzinfo=UTC),
        executor=SimpleNamespace(submit=lambda fn, *a: fn(*a)),
        on_event=events.append,
    )
    sched.running.add(1)
    sched._job(1, "task")
    assert events[-1]["state"] == "error"
    assert events[-1]["screenshot"] == b"png"


def test_default_still_s_is_off(tmp_path):
    dev = record(tmp_path)[1]
    dev.cur = "login"
    clk = FakeClock()
    p = make_player(tmp_path, dev, clk)
    assert p.cfg.still_s == 0
    p.grab()
    clk.t = 100000
    p.grab()  # never frozen when disabled


def test_login_and_mode_play_carry_watch_package(tmp_path, monkeypatch):
    dev = record(tmp_path)[1]
    captured = []

    class FakePlayer:
        def __init__(self, dev, script, assets, cfg=None, *a, **k):
            self.cfg = cfg

        def run(self):
            captured.append((self.cfg.watch_package, self.cfg.still_s))

        def identify(self, img):
            return "login"

        def grab(self):
            return None

    import gamebot.core.runner as runner_mod

    monkeypatch.setattr(runner_mod, "Player", FakePlayer)
    monkeypatch.setattr(runner_mod, "Learner", lambda *a, **k: None)
    game = SimpleNamespace(id=1, package="com.game", popups=[], still_s=180.0)
    login = SimpleNamespace(id="g-login", steps=[SimpleNamespace(from_screen="login")])
    runner = RowRunner.__new__(RowRunner)
    runner.assets_root = tmp_path
    runner.conn = None
    runner.accounts = SimpleNamespace(secrets=lambda aid: None)
    runner.sleep = lambda s: None
    runner.players = {}
    runner.games = SimpleNamespace(get=lambda gid: game)
    runner.scripts = SimpleNamespace(
        for_game=lambda gid, mode: login if mode == "login" else SimpleNamespace(id="g-task")
    )
    runner.device_factory = lambda serial: dev
    runner.ensure_serial = lambda row: "serial"
    row = SimpleNamespace(id=1, game_id=1, account_id="a1")
    assert runner.run(row, "task").ok
    assert captured == [("com.game", 180.0), ("com.game", 180.0)]  # login play, then task play


def fg_player(tmp_path, pkgs):
    dev = record(tmp_path)[1]
    dev.cur = "login"
    it = iter(pkgs)
    dev.foreground_package = lambda: next(it)
    return make_player(tmp_path, dev, FakeClock(), watch_package="com.game", fg_check_s=0.0)


def test_game_lost_needs_three_consecutive_mismatches(tmp_path):
    p = fg_player(tmp_path, ["com.other"] * 3)
    p.grab()
    p.grab()
    with pytest.raises(GameLost):
        p.grab()


def test_fg_match_resets_miss_counter(tmp_path):
    p = fg_player(tmp_path, ["com.other", "com.other", "com.game", "com.other", "com.other"])
    for _ in range(5):
        p.grab()


def test_fg_ignored_packages_do_not_count(tmp_path):
    pkgs = ["com.google.android.gms", "com.android.systemui"] * 5
    p = fg_player(tmp_path, pkgs)
    for _ in range(10):
        p.grab()


def test_fg_ignored_does_not_reset_counter(tmp_path):
    p = fg_player(tmp_path, ["com.other", "com.other", "com.android.systemui", "com.other"])
    p.grab()
    p.grab()
    p.grab()
    with pytest.raises(GameLost):
        p.grab()


def _clock_frame(base, t):
    img = base.copy()
    img[0:20, 100:200] = noise(int(t) + 1000, 100, 20)  # status bar clock only
    return img


def test_status_bar_animation_still_counts_as_frozen(tmp_path):
    dev = record(tmp_path)[1]
    dev.cur = "login"
    clk = FakeClock()
    base = dev.screens["login"].copy()
    dev.on_screencap = lambda d: d.screens.__setitem__("login", _clock_frame(base, clk.t))
    p = make_player(tmp_path, dev, clk, still_s=180.0)
    p.grab()
    clk.t = 100
    p.grab()
    clk.t = 180
    with pytest.raises(ScreenFrozen):
        p.grab()


def test_real_change_resets_frozen_timer(tmp_path):
    dev = record(tmp_path)[1]
    dev.cur = "login"
    clk = FakeClock()
    p = make_player(tmp_path, dev, clk, still_s=180.0)
    p.grab()
    clk.t = 170
    dev.screens["login"] = noise(77, W, H)  # real change
    p.grab()
    clk.t = 340  # 170s since the change
    p.grab()
    clk.t = 350
    with pytest.raises(ScreenFrozen):
        p.grab()
