import pytest
from cdmsync.app import create_app, create_user
from cryptography.exceptions import InvalidTag
from fastapi.testclient import TestClient

from gamebot.core.accounts import AccountRepo, MemoryVault
from gamebot.core.games import Game, GameRepo
from gamebot.core.rows import Row, RowRepo
from gamebot.core.runner import RowRunner
from gamebot.db import connect, init_db
from gamebot.device import Device
from gamebot.emulators import Registry
from gamebot.play import Recorder
from gamebot.script import AssetStore
from gamebot.script.repo import ScriptRepo
from gamebot.sync import SyncClient
from gamebot.sync.crypto import decrypt, encrypt

from .fakes import FakeDevice, make_screen
from .test_m4_m5 import REGION, FakeDriver, Shell


def server():
    app = create_app("sqlite://")
    tok = create_user(app.state.engine, "u")
    return app, tok


def machine(app, tok, root, passphrase=None):
    conn = connect(":memory:")
    init_db(conn)
    vault = MemoryVault()
    http = TestClient(app, headers={"Authorization": f"Bearer {tok}"})
    sc = SyncClient(conn, http, root, vault, passphrase, kdf_iterations=1000)
    return conn, vault, sc


def test_crypto_roundtrip_and_wrong_passphrase():
    blob = encrypt("pass", "pw123", 1000)
    assert "pw123" not in str(blob) and decrypt("pass", blob) == "pw123"
    with pytest.raises(InvalidTag):
        decrypt("other", blob)


def test_two_clients_push_pull_and_run(tmp_path):
    app, tok = server()
    # machine A: records a script, adds account, syncs with password sync enabled
    ra, rb = tmp_path / "a", tmp_path / "b"
    conn_a, vault_a, sync_a = machine(app, tok, ra, "pp")
    fake = FakeDevice(
        {"login": make_screen(1, 11, (120, 300, 120, 50, 21)), "main": make_screen(2, 12)},
        {"login": (120, 300, 120, 50, 21, "main")},
        "login",
    )
    rec = Recorder(fake, AssetStore(ra, "t1"), "t1", "g1", "task", lambda s: None)
    rec.mark_screen("login", REGION)
    rec.record_tap(180, 325, from_screen="login")
    rec.mark_screen("main", REGION)
    rec.script.steps[0].to_screen = "main"
    ScriptRepo(conn_a).save(rec.finish())
    GameRepo(conn_a).save(Game(id="g1", package="com.g"))
    acc = AccountRepo(conn_a, vault_a).add("g1", "main", "bob", "hunter2")
    RowRepo(conn_a).save(
        Row(
            name="row1", game_id="g1", account_id=acc.id, emulator_kind="ldplayer", emulator_ref="3"
        )
    )
    res = sync_a.sync()
    assert res["pushed"] >= 5 and not res["conflicts"]

    # server never sees the plaintext password
    from sqlalchemy import text

    with app.state.engine.begin() as c:
        dump = " ".join(str(tuple(r)) for r in c.execute(text("SELECT data FROM records")))
    assert "hunter2" not in dump

    # machine B pulls and can replay the script on its own emulator
    conn_b, vault_b, sync_b = machine(app, tok, rb, "pp")
    res_b = sync_b.sync()
    assert res_b["applied"] >= 5 and res_b["assets"] >= 3
    assert vault_b.get(acc.id) == "hunter2"
    rows_b = RowRepo(conn_b).list()
    assert rows_b[0].name == "row1" and rows_b[0].emulator_ref == ""  # binding stays local
    fake.cur = "login"
    runner = RowRunner(
        conn_b,
        Registry([FakeDriver()]),
        AccountRepo(conn_b, vault_b),
        rb,
        lambda s: Device(Shell(fake)),
        sleep=lambda s: None,
    )
    row = rows_b[0]
    row.emulator_kind, row.emulator_ref = "fake", "0"
    assert runner.run(row, "task").ok and fake.cur == "main"


def test_conflict_keeps_newer_and_second_sync_is_noop(tmp_path):
    app, tok = server()
    conn_a, vault_a, sa = machine(app, tok, tmp_path / "a")
    conn_b, vault_b, sb = machine(app, tok, tmp_path / "b")
    GameRepo(conn_a).save(Game(id="g", package="v1"))
    sa.sync()
    sb.sync()
    # both edit offline; B edits last
    GameRepo(conn_a).save(Game(id="g", package="from-a"))
    sa.sync()
    GameRepo(conn_b).save(Game(id="g", package="from-b"))
    out = sb.sync()
    assert GameRepo(conn_b).get("g").package == "from-b"
    sa.sync()
    assert GameRepo(conn_a).get("g").package == "from-b"
    assert out["pushed"] == 1 and sa.sync()["pushed"] == 0


def test_passwords_not_synced_without_passphrase(tmp_path):
    app, tok = server()
    conn_a, vault_a, sa = machine(app, tok, tmp_path / "a")
    AccountRepo(conn_a, vault_a).add("g", "l", "u", "secret")
    sa.sync()
    conn_b, vault_b, sb = machine(app, tok, tmp_path / "b", "pp")
    sb.sync()
    assert AccountRepo(conn_b, vault_b).list()[0].username == "u"
    assert vault_b.get(AccountRepo(conn_b, vault_b).list()[0].id) is None


def test_wrong_passphrase_fails_to_pull(tmp_path):
    app, tok = server()
    conn_a, vault_a, sa = machine(app, tok, tmp_path / "a", "right")
    AccountRepo(conn_a, vault_a).add("g", "l", "u", "secret")
    sa.sync()
    _, _, sb = machine(app, tok, tmp_path / "b", "wrong")
    with pytest.raises(InvalidTag):
        sb.sync()
