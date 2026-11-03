from __future__ import annotations

import re
import threading
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass

from ..vision import decode

_EV = re.compile(
    r"^(?:\[\s*(?P<t>\d+\.\d+)\]\s*)?(?P<dev>/dev/input/event\d+):\s*"
    r"(?P<type>EV_\w+)\s+(?P<code>\w+)\s+(?P<val>\w+)\s*$"
)
_RANGE = re.compile(r"(ABS_MT_POSITION_[XY])\s*:.*?min\s+(-?\d+),\s*max\s+(\d+)")
TAP_MAX_PX = 20  # movement below this between down and up counts as a tap


@dataclass(frozen=True)
class Gesture:
    kind: str  # "tap" | "swipe"
    x1: int
    y1: int
    x2: int
    y2: int
    ms: int


def parse_touch_device(props: str) -> tuple[str, dict[str, tuple[int, int]]] | None:
    """Pick the first input device exposing ABS_MT_POSITION_X/Y from `getevent -lp` output.

    Returns (device path, {"X": (min, max), "Y": (min, max)}).
    """
    for block in re.split(r"(?=add device \d+:)", props):
        m = re.match(r"add device \d+:\s*(\S+)", block)
        if not m:
            continue
        rng = {k[-1]: (int(lo), int(hi)) for k, lo, hi in _RANGE.findall(block)}
        if "X" in rng and "Y" in rng:
            return m.group(1), rng
    return None


class GeteventParser:
    """Turns `getevent -lt` lines of one touch device into tap/swipe gestures.

    Only the first finger (slot 0) is tracked. Raw coordinates are scaled to screen pixels.
    """

    def __init__(
        self,
        ranges: dict[str, tuple[int, int]],
        width: int,
        height: int,
        device: str | None = None,
        on_down: Callable[[int, int], None] | None = None,
    ):
        self.ranges, self.size, self.device, self.on_down = ranges, (width, height), device, on_down
        self.slot = 0
        self.touching = False
        self.raw = {"X": None, "Y": None}
        self.start: tuple[int, int, float] | None = None
        self.last: tuple[int, int] = (0, 0)
        self._down = self._up = False
        self._t = 0.0

    def _px(self, axis: str, raw: int) -> int:
        lo, hi = self.ranges[axis]
        size = self.size[0 if axis == "X" else 1]
        return round((raw - lo) * (size - 1) / max(hi - lo, 1))

    def feed(self, line: str) -> Gesture | None:
        m = _EV.match(line.strip())
        if not m or (self.device and m["dev"] != self.device):
            return None
        if m["t"]:
            self._t = float(m["t"])
        typ, code, val = m["type"], m["code"], m["val"]
        if typ == "EV_ABS":
            if code == "ABS_MT_SLOT":
                self.slot = int(val, 16)
            elif self.slot != 0:
                return None
            elif code == "ABS_MT_TRACKING_ID":
                if int(val, 16) == 0xFFFFFFFF:
                    self._up = True
                elif not self.touching:
                    self._down = True
            elif code in ("ABS_MT_POSITION_X", "ABS_MT_POSITION_Y"):
                self.raw[code[-1]] = int(val, 16)
        elif typ == "EV_KEY" and code == "BTN_TOUCH":
            if val == "DOWN" and not self.touching:
                self._down = True
            elif val == "UP":
                self._up = True
        elif typ == "EV_SYN" and code == "SYN_REPORT":
            return self._frame()
        return None

    def _frame(self) -> Gesture | None:
        down, up, self._down, self._up = self._down, self._up, False, False
        if self.raw["X"] is not None and self.raw["Y"] is not None:
            self.last = (self._px("X", self.raw["X"]), self._px("Y", self.raw["Y"]))
        if down and not self.touching:
            self.touching, self.start = True, (*self.last, self._t)
            if self.on_down:
                self.on_down(*self.last)
        if up and self.touching and self.start:
            self.touching = False
            (x1, y1, t0), (x2, y2) = self.start, self.last
            self.start = None
            self.raw = {"X": None, "Y": None}
            ms = max(int((self._t - t0) * 1000), 1)
            if abs(x2 - x1) <= TAP_MAX_PX and abs(y2 - y1) <= TAP_MAX_PX:
                return Gesture("tap", x1, y1, x1, y1, ms)
            return Gesture("swipe", x1, y1, x2, y2, ms)
        return None


def iter_lines(stream: Iterable[bytes | str]) -> Iterator[str]:
    """Re-chunk a byte/str stream (adbutils streaming shell) into lines."""
    buf = ""
    for chunk in stream:
        buf += chunk.decode("utf-8", "replace") if isinstance(chunk, bytes) else chunk
        *done, buf = buf.split("\n")
        yield from done


class LiveRecorder:
    """Records gestures made directly on the emulator window into a `Recorder`.

    The screen is captured on touch-down (before the app reacts) so the template crop shows
    the tapped element; the gesture itself is not re-executed on the device.
    """

    def __init__(self, recorder, lines: Iterable[str], props: str):
        found = parse_touch_device(props)
        if not found:
            raise RuntimeError("no touch input device found in `getevent -lp` output")
        self.rec = recorder
        info = recorder.info
        self._shot: bytes | None = None
        self.parser = GeteventParser(
            found[1], info.width, info.height, found[0], on_down=self._grab
        )
        self.lines = lines
        self.stop = threading.Event()

    def _grab(self, x: int, y: int) -> None:
        self._shot = self.rec.dev.screencap()

    def run(self) -> None:
        for line in self.lines:
            if self.stop.is_set():
                break
            g = self.parser.feed(line)
            if g is None:
                continue
            if g.kind == "tap":
                img = decode(self._shot) if self._shot else None
                self.rec.record_tap(g.x1, g.y1, img=img, execute=False)
            else:
                self.rec.record_swipe(g.x1, g.y1, g.x2, g.y2, g.ms, execute=False)
