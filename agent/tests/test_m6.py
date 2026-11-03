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


def test_deletes_propagate_via_tombstones(tmp_path):
    app, tok = server()
    conn_a, vault_a, sa = machine(app, tok, tmp_path / "a", "pp")
    conn_b, vault_b, sb = machine(app, tok, tmp_path / "b", "pp")
    GameRepo(conn_a).save(Game(id="g", package="p"))
    acc = AccountRepo(conn_a, vault_a).add("g", "l", "u", "pw")
    RowRepo(conn_a).save(Row(name="r1", game_id="g"))
    rec = Recorder(
        FakeDevice({"s": make_screen(1, 11)}, {}, "s"),
        AssetStore(tmp_path / "a", "t1"),
        "t1",
        "g",
        "task",
        lambda s: None,
    )
    ScriptRepo(conn_a).save(rec.finish())
    sa.sync()
    sb.sync()
    assert GameRepo(conn_b).get("g") and ScriptRepo(conn_b).load("t1")
    assert RowRepo(conn_b).list()[0].name == "r1" and vault_b.get(acc.id) == "pw"

    # A deletes everything; B must see it after one sync each
    GameRepo(conn_a).delete("g")
    ScriptRepo(conn_a).delete("t1")
    RowRepo(conn_a).delete(RowRepo(conn_a).list()[0].id)
    AccountRepo(conn_a, vault_a).delete(acc.id)
    assert RowRepo(conn_a).list() == [] and GameRepo(conn_a).list() == []
    assert sa.sync()["pushed"] == 4
    assert sb.sync()["applied"] == 4
    assert GameRepo(conn_b).get("g") is None and ScriptRepo(conn_b).load("t1") is None
    assert RowRepo(conn_b).list() == [] and AccountRepo(conn_b, vault_b).list() == []
    assert vault_b.get(acc.id) is None
    # tombstones are not re-pushed or bounced back
    assert sb.sync()["pushed"] == 0 and sa.sync()["applied"] == 0


def test_recreate_after_delete_wins_over_tombstone(tmp_path):
    app, tok = server()
    conn_a, _, sa = machine(app, tok, tmp_path / "a")
    conn_b, _, sb = machine(app, tok, tmp_path / "b")
    RowRepo(conn_a).save(Row(name="r1", game_id="g1"))
    sa.sync()
    sb.sync()
    RowRepo(conn_a).delete(RowRepo(conn_a).list()[0].id)
    sa.sync()
    sb.sync()
    assert RowRepo(conn_b).list() == []
    RowRepo(conn_b).save(Row(name="r1", game_id="g2"))  # same name re-created on B
    sb.sync()
    sa.sync()
    assert [r.game_id for r in RowRepo(conn_a).list()] == ["g2"]
    assert [r.game_id for r in RowRepo(conn_b).list()] == ["g2"]


def test_old_database_gets_deleted_column():
    conn = connect(":memory:")
    conn.execute(
        "CREATE TABLE games (id TEXT PRIMARY KEY, package TEXT, profile TEXT,"
        " updated_at TEXT, version INTEGER DEFAULT 1)"
    )
    init_db(conn)
    assert "deleted" in {r[1] for r in conn.execute("PRAGMA table_info(games)")}
