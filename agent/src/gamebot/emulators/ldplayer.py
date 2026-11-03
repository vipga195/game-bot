from __future__ import annotations

import subprocess
from collections.abc import Callable

from .base import EmulatorDriver, Instance

Runner = Callable[[list[str]], str]


def run_cmd(args: list[str]) -> str:
    return subprocess.run(args, capture_output=True, text=True, timeout=60, check=True).stdout


class LDPlayerDriver(EmulatorDriver):
    """LDPlayer via ldconsole. Console port of instance i is 5554 + 2*i (adb serial emulator-N)."""

    kind = "ldplayer"

    def __init__(self, console: str = "ldconsole.exe", runner: Runner = run_cmd):
        self.console = console
        self._run = runner

    def scan(self) -> list[Instance]:
        # list2 columns: index,name,top_hwnd,bind_hwnd,android_started,pid,pid_vbox,w,h,dpi
        out: list[Instance] = []
        for line in self._run([self.console, "list2"]).splitlines():
            p = line.strip().split(",")
            if len(p) < 6 or not p[0].isdigit():
                continue
            running = p[4] == "1"
            serial = f"emulator-{5554 + 2 * int(p[0])}" if running else None
            out.append(Instance(self.kind, p[1], p[0], serial, running))
        return out

    def start(self, ref: str) -> None:
        self._run([self.console, "launch", "--index", ref])

    def stop(self, ref: str) -> None:
        self._run([self.console, "quit", "--index", ref])

    def set_resolution(self, ref: str, width: int, height: int, dpi: int) -> bool:
        self._run(
            [self.console, "modify", "--index", ref, "--resolution", f"{width},{height},{dpi}"]
        )
        return True
