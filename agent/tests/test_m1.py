from fastapi.testclient import TestClient

from gamebot.core.accounts import MemoryVault
from gamebot.db import connect, init_db
from gamebot.device import Device
from gamebot.emulators import AdbGenericDriver, LDPlayerDriver, Registry
from gamebot.main import create_app

LIST2 = "0,LDPlayer,0,0,1,111,222,540,960,240\n1,Second,0,0,0,-1,-1,540,960,240\n"


class FakeShell:
    def __init__(self, replies=None):
        self.calls = []
        self.replies = replies or {}

    def shell(self, cmd, encoding="utf-8"):
        self.calls.append(cmd)
        if cmd == "screencap -p":
            return b"\x89PNG"
        return self.replies.get(cmd, "")


def test_db_roundtrip():
    conn = connect(":memory:")
    init_db(conn)
    conn.execute("INSERT INTO rows(name) VALUES ('a')")
    assert conn.execute("SELECT name FROM rows").fetchone()["name"] == "a"


def test_ldplayer_scan_and_cmds():
    calls = []

    def run(args):
        calls.append(args)
        return LIST2

    d = LDPlayerDriver("ldc", run)
    insts = d.scan()
    assert [(i.ref, i.running, i.serial) for i in insts] == [
        ("0", True, "emulator-5554"),
        ("1", False, None),
    ]
    d.start("1")
    d.stop("1")
    assert d.set_resolution("0", 720, 1280, 320)
    assert calls[-1][-1] == "720,1280,320"
    assert calls[1][:2] == ["ldc", "launch"]


def test_registry_dedup():
    ld = LDPlayerDriver("ldc", lambda a: LIST2)
    gen = AdbGenericDriver(lambda: ["emulator-5554", "R58M"])
    found = Registry([gen, ld]).scan()
    serials = [i.serial for i in found]
    assert serials.count("emulator-5554") == 1
    assert {i.kind for i in found if i.serial == "emulator-5554"} == {"ldplayer"}
    assert "R58M" in serials


def test_registry_survives_driver_failure():
    def boom(a):
        raise FileNotFoundError

    found = Registry([LDPlayerDriver("x", boom), AdbGenericDriver(lambda: ["s"])]).scan()
    assert [i.serial for i in found] == ["s"]


def test_device_input_and_screen():
    sh = FakeShell(
        {
            "wm size": "Physical size: 1080x1920\nOverride size: 720x1280\n",
            "wm density": "Physical density: 320\n",
        }
    )
    d = Device(sh)
    assert d.screencap().startswith(b"\x89PNG")
    d.tap(1, 2)
    d.swipe(1, 2, 3, 4, 100)
    d.key(4)
    d.text("a b")
    d.start_app("com.x")
    d.stop_app("com.x")
    d.set_screen(720, 1280, 240)
    d.reset_screen()
    assert "input tap 1 2" in sh.calls and "input text a%sb" in sh.calls
    assert "wm size 720x1280" in sh.calls and "wm density reset" in sh.calls
    info = d.screen_info()
    assert (info.width, info.height, info.dpi) == (720, 1280, 320)


def test_api(tmp_path):
    reg = Registry([LDPlayerDriver("ldc", lambda a: LIST2)])
    c = TestClient(create_app(reg, tmp_path, MemoryVault()))
    assert c.get("/health").json() == {"status": "ok"}
    assert len(c.get("/instances").json()) == 2
