from fastapi.testclient import TestClient

from gamebot.core.accounts import MemoryVault
from gamebot.device import Device
from gamebot.emulators import Registry
from gamebot.main import create_app

from .fakes import two_screen_game
from .test_m4_m5 import Shell


def client(tmp_path):
    fake = two_screen_game()
    app = create_app(Registry([]), tmp_path, MemoryVault(), lambda s: Device(Shell(fake)))
    return TestClient(app), fake


def test_rows_accounts_games(tmp_path):
    c, _ = client(tmp_path)
    r = c.post("/rows", json={"name": "r1", "game_id": "g"}).json()
    assert r["id"] == 1
    assert c.get("/rows").json()[0]["state"] == "idle"
    a = c.post("/accounts", json={"game_id": "g", "label": "l", "username": "u", "password": "p"})
    assert "password" not in a.json() and "p" not in c.get("/accounts").text.replace("u", "")
    assert c.post("/games", json={"id": "g", "package": "com.g"}).status_code == 200
    assert len(c.get("/games").json()) == 1
    assert c.delete("/rows/1").json() == {"ok": True}


def test_recorder_flow(tmp_path):
    c, fake = client(tmp_path)
    assert c.get("/recorder/screen").status_code == 409
    c.post("/recorder/start", json={"serial": "s", "game_id": "g1", "mode": "task"})
    assert c.get("/recorder/screen").content.startswith(b"\x89PNG")
    c.post("/recorder/mark", json={"name": "login", "region": [0.27, 0.03, 0.72, 0.12]})
    c.post("/recorder/tap", json={"x": 180, "y": 325, "from_screen": "login"})
    assert c.post("/recorder/finish").json() == {"script_id": "g1-task", "steps": 1}
