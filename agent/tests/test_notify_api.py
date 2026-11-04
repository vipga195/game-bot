import pytest
from fastapi.testclient import TestClient

from gamebot.core.accounts import MemoryVault
from gamebot.emulators import Registry
from gamebot.main import create_app
from gamebot.notify import repo


@pytest.fixture
def env(tmp_path, monkeypatch):
    sent = []
    fail = {"on": False}

    class FakeChannel:
        def __init__(self, cfg, secret):
            self.cfg, self.secret = cfg, secret

        def send(self, title, text, image=None):
            if fail["on"]:
                raise RuntimeError("boom " + self.secret)
            sent.append((self.secret, title, text))

    monkeypatch.setitem(repo.FACTORIES, "telegram", FakeChannel)
    vault = MemoryVault()
    c = TestClient(create_app(Registry([]), tmp_path, vault))
    yield c, vault, sent, fail


def test_add_list_no_secret_in_response_or_db(env):
    c, vault, _, _ = env
    r = c.post(
        "/notify/channels",
        json={
            "kind": "telegram",
            "name": "ops",
            "level": "error",
            "config": {"chat_id": "42"},
            "secret": "1:TOKEN-XYZ",
        },
    )
    assert r.status_code == 200
    assert "secret" not in r.json()
    assert "1:TOKEN-XYZ" not in r.text
    r = c.get("/notify/channels")
    assert len(r.json()) == 1
    assert r.json()[0]["level"] == "error"
    assert r.json()[0]["config"] == {"chat_id": "42"}
    assert "1:TOKEN-XYZ" not in r.text
    rows = c.app.state.conn.execute("SELECT config FROM notify_channels").fetchall()
    assert all("1:TOKEN-XYZ" not in r[0] for r in rows)
    assert vault.get(f"notify:{r.json()[0]['id']}") == "1:TOKEN-XYZ"
    assert len(c.app.state.notifier.channels) == 1


def test_invalid_kind_and_level_return_400(env):
    c, _, _, _ = env
    for kind, level in [("sms", "error"), ("telegram", "warn")]:
        r = c.post(
            "/notify/channels",
            json={
                "kind": kind,
                "name": "ops",
                "level": level,
                "config": {"chat_id": "42"},
                "secret": "1:TOKEN-BAD",
            },
        )
        assert r.status_code == 400
        assert "1:TOKEN-BAD" not in r.text
    for name in ["", "too long" * 10]:
        r = c.post(
            "/notify/channels",
            json={
                "kind": "telegram",
                "name": name,
                "level": "error",
                "config": {"chat_id": "42"},
                "secret": "1:TOKEN-BAD",
            },
        )
        assert r.status_code == 400
        assert "1:TOKEN-BAD" not in r.text
    for config in [{}, {"chat_id": ""}]:
        r = c.post(
            "/notify/channels",
            json={
                "kind": "telegram",
                "name": "ops",
                "level": "error",
                "config": config,
                "secret": "1:TOKEN-BAD",
            },
        )
        assert r.status_code == 400
        assert "1:TOKEN-BAD" not in r.text


def test_delete_removes_vault_entry_and_notifier_channel(env):
    c, vault, _, _ = env
    r = c.post(
        "/notify/channels",
        json={
            "kind": "telegram",
            "name": "ops",
            "level": "error",
            "config": {"chat_id": "42"},
            "secret": "1:TOKEN-XYZ",
        },
    )
    channel_id = r.json()["id"]
    r = c.delete(f"/notify/channels/{channel_id}")
    assert r.json() == {"ok": True}
    assert vault.get(f"notify:{channel_id}") is None
    r = c.get("/notify/channels")
    assert len(r.json()) == 0
    assert len(c.app.state.notifier.channels) == 0


def test_notify_test_ok(env):
    c, _, sent, _ = env
    r = c.post(
        "/notify/channels",
        json={
            "kind": "telegram",
            "name": "ops",
            "level": "error",
            "config": {"chat_id": "42"},
            "secret": "1:TOKEN-OK",
        },
    )
    channel_id = r.json()["id"]
    r = c.post("/notify/test", json={"id": channel_id})
    assert r.json() == {"ok": True}
    assert sent == [("1:TOKEN-OK", "gamebot test", "test message")]


def test_notify_test_failure_is_generic(env):
    c, _, sent, fail = env
    r = c.post(
        "/notify/channels",
        json={
            "kind": "telegram",
            "name": "ops",
            "level": "error",
            "config": {"chat_id": "42"},
            "secret": "1:TOKEN-FAIL",
        },
    )
    channel_id = r.json()["id"]
    fail["on"] = True
    r = c.post("/notify/test", json={"id": channel_id})
    assert r.json() == {"ok": False, "error": "send failed"}
    assert "1:TOKEN-FAIL" not in r.text
    assert "boom" not in r.text


def test_notify_test_unknown_id_404(env):
    c, _, _, _ = env
    r = c.post("/notify/test", json={"id": "nope"})
    assert r.status_code == 404


def test_teams_add_https_ok(env):
    c, vault, _, _ = env
    r = c.post(
        "/notify/channels",
        json={
            "kind": "teams",
            "name": "ops",
            "level": "error",
            "config": {},
            "secret": "https://x.webhook.office.com/WEBHOOK-SECRET",
        },
    )
    assert r.status_code == 200
    assert "WEBHOOK-SECRET" not in r.text
    rows = c.app.state.conn.execute("SELECT config FROM notify_channels").fetchall()
    assert all("WEBHOOK-SECRET" not in row[0] for row in rows)
    assert vault.get(f"notify:{r.json()['id']}") == "https://x.webhook.office.com/WEBHOOK-SECRET"


def test_teams_add_http_rejected(env):
    c, _, _, _ = env
    r = c.post(
        "/notify/channels",
        json={
            "kind": "teams",
            "name": "ops",
            "level": "error",
            "config": {},
            "secret": "http://example.test/WEBHOOK-SECRET",
        },
    )
    assert r.status_code == 400
    assert "WEBHOOK-SECRET" not in r.text
