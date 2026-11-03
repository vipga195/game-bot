import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine

from cdmsync.app import create_app, create_user, meta

# Set CDM_TEST_DB=postgresql+psycopg://... to run the whole suite against Postgres.
DB = os.environ.get("CDM_TEST_DB", "sqlite://")


def fresh_app(**kw):
    if DB != "sqlite://":
        e = create_engine(DB)
        meta.drop_all(e)
        e.dispose()
    return create_app(DB, **kw)


def setup():
    app = fresh_app()
    tok = create_user(app.state.engine, "u")
    return TestClient(app), {"Authorization": f"Bearer {tok}"}, app


def ch(i, v, t, data=None, kind="script"):
    return {"kind": kind, "id": i, "version": v, "updated_at": t, "data": data or {"v": v}}


def test_auth_required():
    c, h, _ = setup()
    assert c.post("/sync", json={}).status_code == 401
    assert c.post("/sync", json={}, headers={"Authorization": "Bearer nope"}).status_code == 401


def test_push_pull_and_cursor():
    c, h, _ = setup()
    r = c.post("/sync", json={"changes": [ch("a", 1, "2026-01-01T00:00:00")]}, headers=h).json()
    assert r["seq"] == 1 and len(r["changes"]) == 1
    r2 = c.post("/sync", json={"since": 1}, headers=h).json()
    assert r2["changes"] == []


def test_lww_newer_wins_and_loser_archived():
    c, h, app = setup()
    c.post("/sync", json={"changes": [ch("a", 1, "2026-01-01T00:00:00", {"v": "old"})]}, headers=h)
    r = c.post(
        "/sync", json={"changes": [ch("a", 2, "2026-01-02T00:00:00", {"v": "new"})]}, headers=h
    ).json()
    assert r["changes"][-1]["data"] == {"v": "new"}
    # stale write arrives later: server keeps the newer one, reports the conflict
    r = c.post(
        "/sync", json={"changes": [ch("a", 2, "2026-01-01T12:00:00", {"v": "stale"})]}, headers=h
    ).json()
    assert r["conflicts"] == [{"kind": "script", "id": "a", "kept": "server"}]
    got = c.post("/sync", json={"since": 0}, headers=h).json()["changes"][0]
    assert got["data"] == {"v": "new"}
    from sqlalchemy import text

    with app.state.engine.begin() as conn:
        n = conn.execute(text("SELECT count(*) FROM record_history")).scalar()
    assert n == 2  # the replaced old version and the rejected stale one


def test_users_are_isolated():
    c, h, app = setup()
    tok2 = create_user(app.state.engine, "v")
    h2 = {"Authorization": f"Bearer {tok2}"}
    c.post("/sync", json={"changes": [ch("a", 1, "2026-01-01T00:00:00")]}, headers=h)
    assert c.post("/sync", json={}, headers=h2).json()["changes"] == []


def test_blobs():
    c, h, _ = setup()
    assert c.put("/blobs/s1/t.png", content=b"\x89PNG", headers=h).status_code == 200
    assert c.get("/blobs/s1/t.png", headers=h).content == b"\x89PNG"
    assert [b["key"] for b in c.get("/blobs", headers=h).json()] == ["s1/t.png"]
    assert c.get("/blobs/none", headers=h).status_code == 404


def test_tombstone_replicates_and_lww_applies():
    c, h, _ = setup()
    c.post("/sync", json={"changes": [ch("a", 1, "2026-01-01T00:00:00")]}, headers=h)
    tomb = {
        "kind": "script",
        "id": "a",
        "version": 2,
        "updated_at": "2026-01-02T00:00:00",
        "deleted": True,
        "data": None,
    }
    c.post("/sync", json={"changes": [tomb]}, headers=h)
    got = c.post("/sync", json={"since": 0}, headers=h).json()["changes"]
    assert got[0]["deleted"] is True and got[0]["data"] is None
    # an older edit arriving later must not resurrect the record
    r = c.post("/sync", json={"changes": [ch("a", 2, "2026-01-01T12:00:00")]}, headers=h).json()
    assert r["conflicts"] == [{"kind": "script", "id": "a", "kept": "server"}]
    assert c.post("/sync", json={"since": 0}, headers=h).json()["changes"][0]["deleted"] is True
    # a newer re-create does
    c.post("/sync", json={"changes": [ch("a", 3, "2026-01-03T00:00:00")]}, headers=h)
    assert c.post("/sync", json={"since": 0}, headers=h).json()["changes"][0]["deleted"] is False


def test_rate_limit_per_user_and_ip():
    app = fresh_app(rate_limit=3)
    tok = create_user(app.state.engine, "u")
    h = {"Authorization": f"Bearer {tok}"}
    c = TestClient(app)
    assert [c.post("/sync", json={}, headers=h).status_code for _ in range(3)] == [200] * 3
    r = c.post("/sync", json={}, headers=h)
    assert r.status_code == 429 and r.headers["Retry-After"] == "60"
    # bad tokens are throttled by IP too (same client already exhausted here)
    assert c.post("/sync", json={}, headers={"Authorization": "Bearer x"}).status_code == 429


def test_rate_limit_disabled():
    app = fresh_app(rate_limit=0)
    tok = create_user(app.state.engine, "u")
    c = TestClient(app)
    h = {"Authorization": f"Bearer {tok}"}
    assert all(c.post("/sync", json={}, headers=h).status_code == 200 for _ in range(200))


@pytest.mark.skipif(DB == "sqlite://", reason="in-memory SQLite shares one connection")
def test_concurrent_syncs_get_unique_seq():
    from concurrent.futures import ThreadPoolExecutor

    from sqlalchemy import text

    c, h, app = setup()

    def go(i):
        return TestClient(app).post(
            "/sync", json={"changes": [ch(f"r{i}", 1, "2026-01-01")]}, headers=h
        )

    with ThreadPoolExecutor(8) as ex:
        assert all(r.status_code == 200 for r in ex.map(go, range(16)))
    with app.state.engine.begin() as conn:
        row = conn.execute(text("SELECT count(*), count(DISTINCT seq) FROM records")).first()
    assert tuple(row) == (16, 16)
