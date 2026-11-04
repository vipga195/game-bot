import threading
import time

import httpx
import pytest

from gamebot import db
from gamebot.core.accounts import MemoryVault
from gamebot.notify.facebook import FacebookChannel
from gamebot.notify.notifier import Notifier
from gamebot.notify.repo import ChannelRepo
from gamebot.notify.teams import TeamsChannel
from gamebot.notify.telegram import TelegramChannel
from gamebot.notify.zalo import ZaloChannel


class FakeChannel:
    def __init__(self):
        self.sent = []

    def send(self, title, text, image=None):
        self.sent.append((title, text, image))


class DeadChannel:
    def send(self, title, text, image=None):
        raise RuntimeError("boom")


class FakeResp:
    def __init__(self, status_code, body=None):
        self.status_code = status_code
        self._body = body

    def json(self):
        if self._body is None:
            raise ValueError("no json")
        return self._body


def make_clock():
    t = [0.0]

    def clock():
        return t[0]

    return t, clock


def err(row, mode="task", error="x"):
    return {"row": row, "state": "error", "mode": mode, "error": error}


def test_error_event_sends_once():
    ch = FakeChannel()
    n = Notifier([(ch, "all")], clock=make_clock()[1])
    n.handle(err(1))
    n.close()
    assert len(ch.sent) == 1
    assert "row 1" in ch.sent[0][0]


def test_duplicate_within_window_suppressed():
    ch = FakeChannel()
    t, clock = make_clock()
    n = Notifier([(ch, "all")], clock=clock, dedupe_s=300)
    n.handle(err(1))
    n.handle(err(1))
    t[0] += 301
    n.handle(err(1))
    n.close()
    assert len(ch.sent) == 2


def test_dead_channel_does_not_raise_or_block():
    ch = FakeChannel()
    n = Notifier([(DeadChannel(), "all"), (ch, "all")], clock=make_clock()[1])
    n.handle(err(1))
    n.close()
    assert len(ch.sent) == 1


def test_idle_after_error_sends_recovered():
    ch = FakeChannel()
    n = Notifier([(ch, "all")], clock=make_clock()[1])
    n.handle(err(1))
    n.handle({"row": 1, "state": "idle", "mode": "task"})
    n.close()
    assert len(ch.sent) == 2
    assert "recovered" in ch.sent[1][0]


def test_idle_without_prior_error_sends_nothing():
    ch = FakeChannel()
    n = Notifier([(ch, "all")], clock=make_clock()[1])
    n.handle({"row": 2, "state": "idle", "mode": "task"})
    n.close()
    assert ch.sent == []


def test_hourly_cap():
    ch = FakeChannel()
    n = Notifier([(ch, "all")], clock=make_clock()[1], max_per_hour=2)
    n.handle(err(1))
    n.handle(err(2))
    n.handle(err(3))
    n.close()
    assert len(ch.sent) == 2


def test_telegram_photo_vs_message():
    posts = []

    def fake_post(url, data=None, files=None, timeout=None):
        posts.append((url, data, files, timeout))
        return FakeResp(200)

    ch = TelegramChannel("TOKEN", "42", send_image=True, post=fake_post)
    ch.send("t", "body")
    assert posts[0][0].endswith("/sendMessage")
    assert posts[0][1]["chat_id"] == "42"
    assert posts[0][2] is None
    ch.send("t", "body", b"png")
    assert posts[1][0].endswith("/sendPhoto")
    assert "photo" in posts[1][2]
    assert posts[1][3] == 10


def test_telegram_error_does_not_leak_token():
    def bad_post(url, **kw):
        raise httpx.ConnectError("failed " + url)

    ch = TelegramChannel("SECRET123", "42", post=bad_post)
    with pytest.raises(RuntimeError) as exc:
        ch.send("t", "x")
    assert "SECRET123" not in str(exc.value)
    assert exc.value.__cause__ is None


def test_telegram_non_2xx_raises():
    ch = TelegramChannel("SECRET123", "42", post=lambda url, **kw: FakeResp(500))
    with pytest.raises(RuntimeError) as exc:
        ch.send("t", "x")
    assert "SECRET123" not in str(exc.value)


def test_late_event_after_close_is_sent_inline():
    ch = FakeChannel()
    n = Notifier([(ch, "all")])
    n.close()
    n.handle({"row": 1, "state": "error", "mode": "daily", "error": "late"})
    assert len(ch.sent) == 1


def test_error_level_skips_warning():
    err_ch = FakeChannel()
    all_ch = FakeChannel()
    n = Notifier([(err_ch, "error"), (all_ch, "all")], clock=make_clock()[1])
    n.handle({"row": 1, "state": "warning", "mode": "task", "message": "slow"})
    n.handle(err(2))
    n.close()
    assert len(err_ch.sent) == 1 and "row 2" in err_ch.sent[0][0]
    assert len(all_ch.sent) == 2 and "warning" in all_ch.sent[0][0]


def test_set_channels_live_reload():
    a = FakeChannel()
    b = FakeChannel()
    n = Notifier([(a, "error")], clock=make_clock()[1])
    n.set_channels([(b, "error")])
    n.handle(err(1))
    n.close()
    assert a.sent == []
    assert len(b.sent) == 1


def test_teams_payload_is_adaptive_card():
    posts = []

    def fake_post(url, json=None, timeout=None):
        posts.append((url, json, timeout))
        return FakeResp(200)

    ch = TeamsChannel("https://example.test/hook", post=fake_post)
    ch.send("T", "body")
    url, payload, timeout = posts[0]
    card = payload["attachments"][0]
    assert url == "https://example.test/hook"
    assert timeout == 10
    assert payload["type"] == "message"
    assert card["contentType"] == "application/vnd.microsoft.card.adaptive"
    assert card["content"]["type"] == "AdaptiveCard"
    assert card["content"]["body"][0]["text"] == "T"
    assert card["content"]["body"][1]["text"] == "body"


def test_teams_ignores_image_and_truncates_text():
    posts = []

    def fake_post(url, **kw):
        posts.append(kw)
        return FakeResp(200)

    ch = TeamsChannel("https://example.test/hook", post=fake_post)
    ch.send("t", "x" * 5000, b"png")
    assert set(posts[0]) == {"json", "timeout"}
    assert len(posts[0]["json"]["attachments"][0]["content"]["body"][1]["text"]) == 4000


def test_teams_error_does_not_leak_url():
    def bad_post(url, **kw):
        raise httpx.ConnectError("failed " + url)

    ch = TeamsChannel("https://example.test/SECRET123", post=bad_post)
    with pytest.raises(RuntimeError) as exc:
        ch.send("t", "x")
    assert "SECRET123" not in str(exc.value)
    assert exc.value.__cause__ is None


def test_teams_non_2xx_raises():
    ch = TeamsChannel("https://example.test/SECRET123", post=lambda url, **kw: FakeResp(500))
    with pytest.raises(RuntimeError) as exc:
        ch.send("t", "x")
    assert str(exc.value) == "teams send failed: HTTP 500"


def test_teams_202_accepted():
    ch = TeamsChannel("https://example.test/hook", post=lambda url, **kw: FakeResp(202))
    assert ch.send("t", "x") is None


def _capture(status=200, body=None):
    calls = []

    def fake_post(url, **kw):
        calls.append((url, kw))
        return FakeResp(status, body)

    return calls, fake_post


def test_zalo_url_payload_and_timeout():
    calls, fake_post = _capture(200, {"ok": True})
    ZaloChannel("TOK", "42", post=fake_post).send("T", "body")
    url, kw = calls[0]
    assert url == "https://bot-api.zaloplatforms.com/botTOK/sendMessage"
    assert kw == {"json": {"chat_id": "42", "text": "T\nbody"}, "timeout": 10}


def test_zalo_truncates_and_ignores_image():
    calls, fake_post = _capture(200)
    ZaloChannel("TOK", "42", post=fake_post).send("t", "x" * 5000, b"png")
    assert len(calls) == 1
    assert len(calls[0][1]["json"]["text"]) == 2000
    assert set(calls[0][1]) == {"json", "timeout"}


def test_zalo_non_2xx_raises_with_code():
    ch = ZaloChannel("TOK", "42", post=lambda url, **kw: FakeResp(403))
    with pytest.raises(RuntimeError, match="HTTP 403") as exc:
        ch.send("t", "x")
    assert "TOK" not in str(exc.value)


def test_zalo_ok_false_raises():
    ch = ZaloChannel("TOK", "42", post=lambda url, **kw: FakeResp(200, {"ok": False}))
    with pytest.raises(RuntimeError, match="ok=false"):
        ch.send("t", "x")


def test_zalo_error_does_not_leak_token():
    def bad_post(url, **kw):
        raise httpx.ConnectError("failed " + url)

    with pytest.raises(RuntimeError) as exc:
        ZaloChannel("SECRET123", "42", post=bad_post).send("t", "x")
    assert "SECRET123" not in str(exc.value)
    assert exc.value.__cause__ is None


def test_facebook_url_params_payload_and_timeout():
    calls, fake_post = _capture(200)
    FacebookChannel("PTOK", "111", "222", post=fake_post).send("T", "body", b"png")
    url, kw = calls[0]
    assert url == "https://graph.facebook.com/v26.0/111/messages"
    assert kw == {
        "params": {"access_token": "PTOK"},
        "json": {
            "recipient": {"id": "222"},
            "messaging_type": "RESPONSE",
            "message": {"text": "T\nbody"},
        },
        "timeout": 10,
    }


def test_facebook_truncates_text():
    calls, fake_post = _capture(200)
    FacebookChannel("PTOK", "111", "222", post=fake_post).send("t", "x" * 5000)
    assert len(calls[0][1]["json"]["message"]["text"]) == 2000


def test_facebook_non_2xx_mentions_window_and_code():
    ch = FacebookChannel("PTOK", "111", "222", post=lambda url, **kw: FakeResp(400))
    with pytest.raises(RuntimeError) as exc:
        ch.send("t", "x")
    assert "HTTP 400" in str(exc.value)
    assert "24h" in str(exc.value)
    assert "PTOK" not in str(exc.value)


def test_facebook_error_does_not_leak_token():
    def bad_post(url, **kw):
        raise httpx.ConnectError("failed " + url + kw["params"]["access_token"])

    with pytest.raises(RuntimeError) as exc:
        FacebookChannel("SECRET123", "111", "222", post=bad_post).send("t", "x")
    assert "SECRET123" not in str(exc.value)
    assert exc.value.__cause__ is None


@pytest.fixture
def repo_env(tmp_path):
    conn = db.connect(str(tmp_path / "t.db"))
    db.init_db(conn)
    vault = MemoryVault()
    yield ChannelRepo(conn, vault), conn, vault
    conn.close()


def test_repo_add_zalo_stores_secret_in_vault_only(repo_env):
    repo, conn, vault = repo_env
    out = repo.add("zalo", "z", {"chat_id": "c1", "junk": "x"}, "ZSECRET")
    assert out["config"] == {"chat_id": "c1"}
    assert "ZSECRET" not in str(out)
    assert vault.get(f"notify:{out['id']}") == "ZSECRET"
    rows = conn.execute("SELECT * FROM notify_channels").fetchall()
    assert len(rows) == 1
    assert all("ZSECRET" not in str(v) for v in tuple(rows[0]))


def test_repo_add_facebook_stores_secret_in_vault_only(repo_env):
    repo, conn, vault = repo_env
    out = repo.add("facebook", "f", {"page_id": "111", "recipient_id": "222"}, "FSECRET")
    assert out["config"] == {"page_id": "111", "recipient_id": "222"}
    assert "FSECRET" not in str(out)
    assert vault.get(f"notify:{out['id']}") == "FSECRET"
    rows = conn.execute("SELECT * FROM notify_channels").fetchall()
    assert all("FSECRET" not in str(v) for v in tuple(rows[0]))


@pytest.mark.parametrize(
    "kind,config",
    [
        ("zalo", {}),
        ("zalo", {"chat_id": ""}),
        ("facebook", {"recipient_id": "222"}),
        ("facebook", {"page_id": "111"}),
        ("facebook", {"page_id": "abc", "recipient_id": "222"}),
        ("facebook", {"page_id": "111", "recipient_id": "2x2"}),
    ],
)
def test_repo_add_invalid_config_raises(repo_env, kind, config):
    repo, conn, vault = repo_env
    with pytest.raises(ValueError):
        repo.add(kind, "n", config, "SECRET")
    assert conn.execute("SELECT COUNT(*) FROM notify_channels").fetchone()[0] == 0
    assert vault._d == {}


def test_repo_build_returns_zalo_and_facebook_channels(repo_env):
    repo, _, _ = repo_env
    repo.add("zalo", "z", {"chat_id": "c1"}, "ZSECRET", level="all")
    repo.add("facebook", "f", {"page_id": "111", "recipient_id": "222"}, "FSECRET")
    built = {type(ch): (ch, lvl) for ch, lvl in repo.build()}
    zalo, zlvl = built[ZaloChannel]
    fb, flvl = built[FacebookChannel]
    assert (zalo.token, zalo.chat_id, zlvl) == ("ZSECRET", "c1", "all")
    assert (fb.page_token, fb.page_id, fb.recipient_id, flvl) == ("FSECRET", "111", "222", "error")


# ---- telegram send_image ----


def test_telegram_image_ignored_by_default():
    posts = []

    def fake_post(url, data=None, files=None, timeout=None):
        posts.append((url, files))
        return FakeResp(200)

    TelegramChannel("TOKEN", "42", post=fake_post).send("t", "body", b"png")
    assert posts[0][0].endswith("/sendMessage")
    assert posts[0][1] is None


def test_repo_telegram_send_image_round_trip(repo_env):
    repo, _, _ = repo_env
    out = repo.add("telegram", "t", {"chat_id": "42", "send_image": True}, "123:abc")
    assert out["config"] == {"chat_id": "42", "send_image": True}
    assert repo.list()[0]["config"]["send_image"] is True
    assert repo.build()[0][0].send_image is True


def test_repo_telegram_send_image_default_and_non_bool(repo_env):
    repo, _, _ = repo_env
    repo.add("telegram", "a", {"chat_id": "42"}, "123:abc")
    out = repo.add("telegram", "b", {"chat_id": "42", "send_image": "yes"}, "123:abc")
    assert "send_image" not in out["config"]
    assert [c.send_image for c, _ in repo.build()] == [False, False]


# ---- teams host allowlist ----


@pytest.mark.parametrize(
    "url",
    [
        "https://contoso.webhook.office.com/webhookb2/a@b/IncomingWebhook/c/d",
        "https://prod-12.westus.logic.azure.com:443/workflows/abc?sig=x",
        "https://abc.environment.api.powerplatform.com:443/powerautomate/x?sig=y",
    ],
)
def test_repo_teams_accepts_allowed_hosts(repo_env, url):
    repo, _, _ = repo_env
    assert repo.add("teams", "t", {}, url)["kind"] == "teams"


@pytest.mark.parametrize(
    "url",
    [
        "https://evil.com/webhook.office.com",
        "https://webhook.office.com.evil.com/x",
        "https://evil.com\\@x.webhook.office.com/x",
        "https://x.webhook.office.com@evil.com/x",
        "https://user:pw@x.webhook.office.com/x",
        "http://x.webhook.office.com/x",
        "https://webhook.office.com/x",
        "https://evilwebhook.office.com/x",
        "https://10.0.0.1/x",
        "https://[::1]/x",
        "https://x.webhook.office.com:bad/x",
        "https://outlook.office.com/webhook/x",
        "",
    ],
)
def test_repo_teams_rejects_bad_hosts(repo_env, url):
    repo, conn, vault = repo_env
    with pytest.raises(ValueError):
        repo.add("teams", "t", {}, url)
    assert conn.execute("SELECT COUNT(*) FROM notify_channels").fetchone()[0] == 0
    assert vault._d == {}


# ---- token / chat id validation ----


@pytest.mark.parametrize(
    "kind,config,secret",
    [
        ("telegram", {"chat_id": "42"}, "nocolon"),
        ("telegram", {"chat_id": "42"}, "12:ab/cd"),
        ("telegram", {"chat_id": "42"}, "12:ab cd"),
        ("telegram", {"chat_id": "4x2"}, "12:abc"),
        ("telegram", {"chat_id": "@"}, "12:abc"),
        ("telegram", {"chat_id": "42\n"}, "12:abc"),
        ("zalo", {"chat_id": "c 1"}, "tok"),
        ("zalo", {"chat_id": "c/1"}, "tok"),
        ("zalo", {"chat_id": "c1"}, "to/k"),
        ("zalo", {"chat_id": "c1"}, "to?k"),
        ("zalo", {"chat_id": "c1"}, "to#k"),
        ("zalo", {"chat_id": "c1"}, "to k"),
    ],
)
def test_repo_rejects_malformed_token_or_chat(repo_env, kind, config, secret):
    repo, _, vault = repo_env
    with pytest.raises(ValueError):
        repo.add(kind, "n", config, secret)
    assert vault._d == {}


@pytest.mark.parametrize("chat", ["42", "-100123", "@mychan"])
def test_repo_telegram_valid_chat_ids(repo_env, chat):
    repo, _, _ = repo_env
    assert repo.add("telegram", "t", {"chat_id": chat}, "123:Ab_-9")["config"]["chat_id"] == chat


def test_repo_zalo_valid_token(repo_env):
    repo, _, _ = repo_env
    assert repo.add("zalo", "z", {"chat_id": "c_1-x"}, "a1:B.2_-")["kind"] == "zalo"


# ---- notifier robustness ----


class SlowChannel:
    def __init__(self):
        self.sent = []

    def send(self, title, text, image=None):
        time.sleep(0.05)
        self.sent.append(title)


def test_close_delivers_all_queued_events():
    ch = SlowChannel()
    n = Notifier([(ch, "all")], max_per_hour=100)
    for i in range(10):
        n.handle(err(i))
    n.close()
    assert len(ch.sent) == 10


def test_late_handle_after_close_does_not_hold_lock():
    seen = []

    class LockProbe:
        def send(self, title, text, image=None):
            got = n._lock.acquire(timeout=1)
            seen.append(got)
            if got:
                n._lock.release()

    n = Notifier([(LockProbe(), "all")])
    n.close()
    t = threading.Thread(target=n.handle, args=(err(1),))
    t.start()
    t.join(3)
    assert seen == [True]


def test_worker_survives_deliver_exception():
    ch = FakeChannel()
    n = Notifier([(ch, "all")])
    real = n._deliver
    calls = []

    def flaky(item):
        calls.append(item)
        if len(calls) == 1:
            raise RuntimeError("boom")
        real(item)

    n._deliver = flaky
    n.handle(err(1))
    n.handle(err(2))
    n.close()
    assert len(calls) == 2
    assert len(ch.sent) == 1


def test_last_map_is_pruned():
    t, clock = make_clock()
    n = Notifier([], clock=clock, dedupe_s=10)
    for i in range(1001):
        n.handle(err(i))
    t[0] = 100
    n.handle(err(5000))
    assert len(n._last) == 1
    n.close()
