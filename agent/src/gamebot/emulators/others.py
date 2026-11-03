"""BlueStacks / Nox / MEmu / Android Emulator / Genymotion drivers.

All command output formats below are written from documentation/memory and have NOT been
verified against real installs (see README): every driver takes an injectable runner so the
parsing is unit-tested on sample output only.
"""

from __future__ import annotations

import re
import subprocess
from collections.abc import Callable

from .base import EmulatorDriver, Instance
from .ldplayer import Runner, run_cmd


def _adb_serials() -> set[str]:
    from adbutils import adb

    return {d.serial for d in adb.device_list()}


class MEmuDriver(EmulatorDriver):
    """memuc listvms rows: index,name,top_hwnd,bind_hwnd,running,pid,... ; adb port 21503+10*i."""

    kind = "memu"

    def __init__(self, console: str = "memuc.exe", runner: Runner = run_cmd):
        self.console, self._run = console, runner

    def scan(self) -> list[Instance]:
        out = []
        for line in self._run([self.console, "listvms"]).splitlines():
            p = line.strip().split(",")
            if len(p) < 5 or not p[0].isdigit():
                continue
            running = p[4] == "1"
            serial = f"127.0.0.1:{21503 + 10 * int(p[0])}" if running else None
            out.append(Instance(self.kind, p[1], p[0], serial, running))
        return out

    def start(self, ref: str) -> None:
        self._run([self.console, "start", "-i", ref])

    def stop(self, ref: str) -> None:
        self._run([self.console, "stop", "-i", ref])

    def set_resolution(self, ref: str, width: int, height: int, dpi: int) -> bool:
        for key, val in (
            ("resolution_width", width),
            ("resolution_height", height),
            ("vbox_dpi", dpi),
        ):
            self._run([self.console, "setconfigex", "-i", ref, key, str(val)])
        return True


class NoxDriver(EmulatorDriver):
    """NoxConsole list (first CSV column = instance name); adb port 62001 + position."""

    kind = "nox"

    def __init__(
        self,
        console: str = "NoxConsole.exe",
        runner: Runner = run_cmd,
        serials: Callable[[], set[str]] = _adb_serials,
    ):
        self.console, self._run, self._serials = console, runner, serials

    def scan(self) -> list[Instance]:
        live, out = self._serials(), []
        names = [
            ln.split(",")[0].strip()
            for ln in self._run([self.console, "list"]).splitlines()
            if ln.strip()
        ]
        for i, name in enumerate(names):
            serial = f"127.0.0.1:{62001 + i}"
            running = serial in live
            out.append(Instance(self.kind, name, name, serial if running else None, running))
        return out

    def start(self, ref: str) -> None:
        self._run([self.console, "launch", f"-name:{ref}"])

    def stop(self, ref: str) -> None:
        self._run([self.console, "quit", f"-name:{ref}"])

    def set_resolution(self, ref: str, width: int, height: int, dpi: int) -> bool:
        self._run(
            [self.console, "modify", f"-name:{ref}", f"-resolution:{width},{height}", f"-dpi:{dpi}"]
        )
        return True


class BlueStacksDriver(EmulatorDriver):
    """Instances and adb ports are read from bluestacks.conf (bst.instance.<name>.adb_port)."""

    kind = "bluestacks"
    _PORT = re.compile(r'^bst\.instance\.([^.]+)\.adb_port="(\d+)"', re.M)

    def __init__(
        self,
        conf_text: Callable[[], str],
        player: str = "HD-Player.exe",
        serials: Callable[[], set[str]] = _adb_serials,
        launcher: Callable[[list[str]], None] = lambda a: subprocess.Popen(a),  # noqa: S603
        adb_shell: Callable[[str, str], None] | None = None,
    ):
        self._conf, self.player, self._serials = conf_text, player, serials
        self._launch, self._shell = launcher, adb_shell

    def scan(self) -> list[Instance]:
        live, out = self._serials(), []
        for name, port in self._PORT.findall(self._conf()):
            serial = f"127.0.0.1:{port}"
            running = serial in live or f"emulator-{int(port) - 1}" in live
            out.append(Instance(self.kind, name, name, serial if running else None, running))
        return out

    def start(self, ref: str) -> None:
        self._launch([self.player, "--instance", ref])

    def stop(self, ref: str) -> None:
        serial = self.adb_serial(ref)
        if serial and self._shell:
            self._shell(serial, "reboot -p")  # no documented per-instance quit command


class AndroidEmulatorDriver(EmulatorDriver):
    """AVDs from `emulator -list-avds`; running ones found via `adb -s emulator-N emu avd name`."""

    kind = "avd"

    def __init__(
        self,
        emulator: str = "emulator",
        runner: Runner = run_cmd,
        launcher: Callable[[list[str]], None] = lambda a: subprocess.Popen(a),  # noqa: S603
        serials: Callable[[], set[str]] = _adb_serials,
        avd_name: Callable[[str], str] | None = None,
    ):
        self.emulator, self._run, self._launch = emulator, runner, launcher
        self._serials, self._avd_name = serials, avd_name or (lambda s: "")

    def scan(self) -> list[Instance]:
        running = {self._avd_name(s): s for s in self._serials() if s.startswith("emulator-")}
        out = []
        for name in self._run([self.emulator, "-list-avds"]).split():
            serial = running.get(name)
            out.append(Instance(self.kind, name, name, serial, serial is not None))
        return out

    def start(self, ref: str) -> None:
        self._launch([self.emulator, "-avd", ref])

    def stop(self, ref: str) -> None:
        serial = self.adb_serial(ref)
        if serial:
            self._run(["adb", "-s", serial, "emu", "kill"])


class GenymotionDriver(EmulatorDriver):
    """gmtool admin list rows: `State | ADB Serial | UUID | Name` (serial 0.0.0.0:0 when off)."""

    kind = "genymotion"

    def __init__(self, gmtool: str = "gmtool", runner: Runner = run_cmd):
        self.gmtool, self._run = gmtool, runner

    def scan(self) -> list[Instance]:
        out = []
        for line in self._run([self.gmtool, "admin", "list"]).splitlines():
            parts = [p.strip() for p in line.split("|")]
            if len(parts) < 4 or parts[0] not in ("On", "Off"):
                continue
            running = parts[0] == "On"
            out.append(
                Instance(self.kind, parts[3], parts[3], parts[1] if running else None, running)
            )
        return out

    def start(self, ref: str) -> None:
        self._run([self.gmtool, "admin", "start", ref])

    def stop(self, ref: str) -> None:
        self._run([self.gmtool, "admin", "stop", ref])
