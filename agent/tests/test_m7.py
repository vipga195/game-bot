from gamebot.emulators import (
    AndroidEmulatorDriver,
    BlueStacksDriver,
    GenymotionDriver,
    MEmuDriver,
    NoxDriver,
    Registry,
)


def recorder():
    calls = []
    return calls, lambda a: (calls.append(a), "")[1]


def test_memu():
    calls = []

    def run(a):
        calls.append(a)
        return "0,MEmu,1,2,1,99\n1,MEmu_1,0,0,0,-1\n"

    d = MEmuDriver("memuc", run)
    s = d.scan()
    assert [(i.ref, i.serial) for i in s] == [("0", "127.0.0.1:21503"), ("1", None)]
    d.start("1")
    d.stop("1")
    assert d.set_resolution("0", 720, 1280, 240)
    assert ["memuc", "start", "-i", "1"] in calls and [
        "memuc",
        "setconfigex",
        "-i",
        "0",
        "vbox_dpi",
        "240",
    ] in calls


def test_nox():
    calls = []

    def run(a):
        calls.append(a)
        return "Nox,x\nNox_1,y\n"

    d = NoxDriver("nc", run, lambda: {"127.0.0.1:62002"})
    s = d.scan()
    assert [(i.name, i.running) for i in s] == [("Nox", False), ("Nox_1", True)]
    d.start("Nox")
    d.set_resolution("Nox", 720, 1280, 240)
    assert ["nc", "launch", "-name:Nox"] in calls and [
        "nc",
        "modify",
        "-name:Nox",
        "-resolution:720,1280",
        "-dpi:240",
    ] in calls


def test_bluestacks():
    conf = 'bst.instance.Pie64.adb_port="5555"\nbst.instance.Pie64_1.adb_port="5565"\nother="1"\n'
    launched, shells = [], []
    d = BlueStacksDriver(
        lambda: conf,
        "HD",
        lambda: {"127.0.0.1:5565"},
        launched.append,
        lambda s, c: shells.append((s, c)),
    )
    s = d.scan()
    assert [(i.name, i.running) for i in s] == [("Pie64", False), ("Pie64_1", True)]
    d.start("Pie64")
    d.stop("Pie64_1")
    assert launched == [["HD", "--instance", "Pie64"]] and shells == [
        ("127.0.0.1:5565", "reboot -p")
    ]


def test_android_emulator():
    calls, launched = [], []

    def run(a):
        calls.append(a)
        return "Pixel_6\nPixel_7\n"

    d = AndroidEmulatorDriver(
        "emu", run, launched.append, lambda: {"emulator-5554", "R5"}, lambda s: "Pixel_7"
    )
    s = d.scan()
    assert [(i.name, i.serial) for i in s] == [("Pixel_6", None), ("Pixel_7", "emulator-5554")]
    d.start("Pixel_6")
    d.stop("Pixel_7")
    assert launched == [["emu", "-avd", "Pixel_6"]] and calls[-1] == [
        "adb",
        "-s",
        "emulator-5554",
        "emu",
        "kill",
    ]


def test_genymotion():
    out = (
        "State | ADB Serial | UUID | Name\n"
        "On | 192.168.56.101:5555 | abc | Pixel\n"
        "Off | 0.0.0.0:0 | def | Tablet\n"
    )
    d = GenymotionDriver("gm", lambda a: out)
    s = d.scan()
    assert [(i.name, i.serial) for i in s] == [("Pixel", "192.168.56.101:5555"), ("Tablet", None)]


def test_registry_with_all_drivers_tolerates_missing_tools():
    def boom(a):
        raise FileNotFoundError

    reg = Registry([MEmuDriver("x", boom), NoxDriver("x", boom, set), GenymotionDriver("x", boom)])
    assert reg.scan() == []
