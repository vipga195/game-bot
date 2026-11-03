import cv2

from gamebot.db import connect, init_db
from gamebot.learn import Learner, PopupHandler
from gamebot.play import Player, Recorder
from gamebot.script import AssetStore

from .fakes import FakeDevice, make_screen, two_screen_game


def setup(tmp_path):
    dev = two_screen_game()
    assets = AssetStore(tmp_path, "s1")
    rec = Recorder(dev, assets, "s1", "g1", sleep=lambda s: None)
    rec.mark_screen("login", (100 / 360, 20 / 640, 260 / 360, 80 / 640))
    rec.record_tap(180, 325, from_screen="login")
    rec.mark_screen("main", (100 / 360, 20 / 640, 260 / 360, 80 / 640))
    rec.script.steps[0].to_screen = "main"
    conn = connect(":memory:")
    init_db(conn)
    dev.cur = "login"
    return dev, assets, rec.finish(), conn


def test_stats_recorded(tmp_path):
    dev, assets, script, conn = setup(tmp_path)
    L = Learner(conn, script, assets)
    Player(dev, script, assets, hooks=L, sleep=lambda s: None).run()
    st = L.stats("s1")
    assert st["success"] == 1 and st["fail"] == 0 and st["avg_wait_ms"] is not None


def test_variant_learned_when_button_rescaled(tmp_path):
    dev, assets, script, conn = setup(tmp_path)
    L = Learner(conn, script, assets)
    # the whole target area is drawn 10% smaller -> only a scaled match works
    login = make_screen(1, 11)
    small = cv2.resize(
        dev.screens["login"][265:385, 120:240], None, fx=0.9, fy=0.9, interpolation=cv2.INTER_AREA
    )
    login[265 : 265 + small.shape[0], 120 : 120 + small.shape[1]] = small
    dev.screens["login"] = login
    dev.buttons["login"] = (120, 296, 108, 45, 0, "main")
    Player(dev, script, assets, hooks=L, sleep=lambda s: None).run()
    assert dev.cur == "main"
    chg = L.changes()
    assert chg and chg[0]["kind"] == "variant"
    assert L.variants(script.steps[0])[1].endswith("~v1")
    assert L.undo(chg[0]["id"]) and not L.changes()


def test_popup_handler_dismisses_overlay(tmp_path):
    dev, assets, script, conn = setup(tmp_path)
    popup_assets = AssetStore(tmp_path, "game_g1")
    L = Learner(conn, script, assets, popup_assets)
    clean = dev.screens["login"].copy()
    popup_img = make_screen(1, 11, (120, 300, 120, 50, 21))
    popup_img[200:260, 60:300] = make_screen(77, 78)[200:260, 60:300]  # covers nothing important
    popup_img[100:300, 60:300] = make_screen(77, 78)[100:300, 60:300]  # covers title & button
    dev.screens["popup"] = popup_img
    dev.screens["login"] = clean
    dev.buttons["popup"] = (200, 120, 40, 40, 0, "login")
    L.teach_popup(PopupHandler("ad", "popup_ad", "tap"), popup_img[120:160, 200:240])
    dev.cur = "popup"
    Player(dev, script, assets, hooks=L, sleep=lambda s: None).run()
    assert dev.cur == "main"


def test_reteach_adds_variant(tmp_path):
    dev, assets, script, conn = setup(tmp_path)
    L = Learner(conn, script, assets)
    name = L.reteach(script.steps[0], dev.screens["login"], 180, 325)
    # identical to the primary pixels -> rejected as duplicate
    assert name is None
    other = make_screen(1, 11, (200, 400, 120, 50, 21))
    assert L.reteach(script.steps[0], other, 260, 425)


def test_fakedevice_unused_import():
    assert FakeDevice
