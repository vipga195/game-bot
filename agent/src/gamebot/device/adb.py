from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Protocol


class Shell(Protocol):
    def shell(self, cmd: str, encoding: str | None = "utf-8") -> str | bytes: ...


@dataclass(frozen=True)
class ScreenInfo:
    width: int
    height: int
    dpi: int


def connect_serial(serial: str) -> Shell:
    from adbutils import adb

    return adb.device(serial)  # type: ignore[return-value]


class Device:
    """Thin ADB wrapper. `shell` is injectable so tests never touch adb."""

    def __init__(self, shell: Shell):
        self.sh = shell

    def _s(self, cmd: str) -> str:
        return str(self.sh.shell(cmd))

    def screencap(self) -> bytes:
        data = self.sh.shell("screencap -p", encoding=None)
        assert isinstance(data, bytes)
        return data

    def tap(self, x: int, y: int) -> None:
        self._s(f"input tap {int(x)} {int(y)}")

    def swipe(self, x1: int, y1: int, x2: int, y2: int, ms: int = 300) -> None:
        self._s(f"input swipe {int(x1)} {int(y1)} {int(x2)} {int(y2)} {int(ms)}")

    def key(self, keycode: int | str) -> None:
        self._s(f"input keyevent {keycode}")

    def text(self, value: str) -> None:
        # `input text` needs %s for spaces and shell-escaping of metacharacters
        esc = re.sub(r"([^A-Za-z0-9_.,:@/+-])", r"\\\1", value.replace(" ", "%s"))
        esc = esc.replace("\\%s", "%s")
        self._s(f"input text {esc}")

    def start_app(self, package: str) -> None:
        self._s(f"monkey -p {package} -c android.intent.category.LAUNCHER 1")

    def stop_app(self, package: str) -> None:
        self._s(f"am force-stop {package}")

    def foreground_package(self) -> str | None:
        m = re.search(r"mCurrentFocus.*?\s([\w.]+)/", self._s("dumpsys window windows"))
        return m.group(1) if m else None

    def screen_info(self) -> ScreenInfo:
        size = self._s("wm size")
        dens = self._s("wm density")
        # "Override size" (if any) is listed after "Physical size" and is the effective one
        sizes = re.findall(r"(\d+)x(\d+)", size)
        dpis = re.findall(r"density:\s*(\d+)", dens)
        if not sizes or not dpis:
            raise RuntimeError(f"cannot parse screen info: {size!r} {dens!r}")
        w, h = sizes[-1]
        return ScreenInfo(int(w), int(h), int(dpis[-1]))

    def set_screen(self, width: int, height: int, dpi: int) -> None:
        self._s(f"wm size {width}x{height}")
        self._s(f"wm density {dpi}")

    def reset_screen(self) -> None:
        self._s("wm size reset")
        self._s("wm density reset")
