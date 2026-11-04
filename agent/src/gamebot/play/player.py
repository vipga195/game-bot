from __future__ import annotations

import random
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Protocol

import cv2
import numpy as np

from ..script import AssetStore, Script, Step
from ..vision import decode, find_template, identify_screen, letterbox
from ..vision.match import DEFAULT_SCALES


class ScreenChanged(Exception):
    """Screen size/DPI changed mid-run: stop and report instead of tapping blind."""


class StepFailed(Exception):
    def __init__(self, step: Step, reason: str, screenshot: bytes | None = None):
        super().__init__(f"{step.id}: {reason}")
        self.step, self.reason, self.screenshot = step, reason, screenshot


class GameLost(Exception):
    """Game left the foreground: stop instead of tapping blind."""


class ScreenFrozen(Exception):
    """Screen unchanged for too long: game likely hung."""


class Hooks(Protocol):
    """Extension points used by the learner (M3)."""

    def recover(self, player: Player, step: Step, screen: np.ndarray) -> bool: ...
    def variants(self, step: Step) -> list[str]: ...
    def record(self, step: Step, ok: bool, wait_ms: int) -> None: ...
    def on_match(self, step: Step, img: np.ndarray, x: int, y: int, scale: float) -> None: ...


class NullHooks:
    def recover(self, player, step, screen) -> bool:
        return False

    def variants(self, step) -> list[str]:
        return [step.template] if step.template else []

    def record(self, step, ok, wait_ms) -> None:
        pass

    def on_match(self, step, img, x, y, scale) -> None:
        pass


@dataclass
class PlayerConfig:
    jitter_px: int = 3
    screen_timeout: float = 8.0
    poll: float = 0.5
    retries: int = 2
    scales: tuple[float, ...] = DEFAULT_SCALES
    force_size: bool = True
    secrets: Callable[[str], str] | None = None  # resolves "{username}" / "{password}"
    events: list = field(default_factory=list)
    watch_package: str | None = None
    fg_check_s: float = 5.0
    still_s: float = 0.0  # 0 (default) disables the frozen-screen check
    still_diff: float = 2.0  # mean abs diff (0-255) of thumbnails below which frames are "same"
    fg_misses: int = 3  # consecutive foreground mismatches before GameLost
    fg_ignore: tuple[str, ...] = ("com.google.android.gms", "com.android.systemui")


def _thumb(raw: bytes) -> np.ndarray:
    """Small grayscale thumbnail without the status-bar rows (clock/battery noise)."""
    img = decode(raw)
    img = img[int(img.shape[0] * 0.06) :]
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    return cv2.resize(gray, (48, 27), interpolation=cv2.INTER_AREA)


def _diff(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.abs(a.astype(np.int16) - b.astype(np.int16)).mean())


class Player:
    def __init__(
        self,
        device,
        script: Script,
        assets: AssetStore,
        cfg: PlayerConfig | None = None,
        hooks: Hooks | None = None,
        sleep: Callable[[float], None] = time.sleep,
        rng: random.Random | None = None,
        clock: Callable[[], float] = time.monotonic,
    ):
        self.dev, self.script, self.assets = device, script, assets
        self.cfg, self.hooks = cfg or PlayerConfig(), hooks or NullHooks()
        self.sleep, self.rng, self.clock = sleep, rng or random.Random(), clock
        self.paused = False
        self._letterbox = False
        self._expected: tuple[int, int, int] | None = None
        self._last_fg = self.clock()
        self._last_thumb: np.ndarray | None = None
        self._fg_miss = 0
        self._still_since = self.clock()

    # ---- screen handling -------------------------------------------------
    def _check_size(self) -> None:
        i = self.dev.screen_info()
        if self._expected and (i.width, i.height, i.dpi) != self._expected:
            raise ScreenChanged(f"screen changed to {i.width}x{i.height}@{i.dpi}")

    def _watch(self, raw: bytes) -> None:
        now = self.clock()
        if self.cfg.watch_package and now - self._last_fg >= self.cfg.fg_check_s:
            self._last_fg = now
            pkg = self.dev.foreground_package()
            if pkg is None or pkg == self.cfg.watch_package or pkg in self.cfg.fg_ignore:
                if pkg == self.cfg.watch_package:
                    self._fg_miss = 0
            else:
                self._fg_miss += 1
                if self._fg_miss >= self.cfg.fg_misses:
                    raise GameLost(f"game not in foreground: {pkg}")
        if self.cfg.still_s > 0:
            thumb = _thumb(raw)
            last = self._last_thumb
            if (
                last is None
                or last.shape != thumb.shape
                or _diff(last, thumb) >= self.cfg.still_diff
            ):
                self._last_thumb, self._still_since = thumb, now
            elif now - self._still_since >= self.cfg.still_s:
                raise ScreenFrozen(f"screen unchanged for {self.cfg.still_s:.0f}s")

    def grab(self) -> np.ndarray:
        """Current screen normalised to the script's reference size (letterboxed if needed)."""
        self._check_size()
        raw = self.dev.screencap()
        img = decode(raw)
        self._watch(raw)
        if self._letterbox:
            img, self._scale, self._ox, self._oy = letterbox(
                img, self.script.ref_width, self.script.ref_height
            )
        return img

    def _real(self, x: int, y: int) -> tuple[int, int]:
        if not self._letterbox:
            return x, y
        return round((x - self._ox) / self._scale), round((y - self._oy) / self._scale)

    def fingerprints(self) -> dict[str, list[np.ndarray]]:
        out = {}
        for name, assets in self.script.screens.items():
            imgs = [a for a in (self.assets.load(n) for n in assets) if a is not None]
            if imgs:
                out[name] = imgs
        return out

    def identify(self, img: np.ndarray) -> str | None:
        return identify_screen(img, self.fingerprints(), scales=self.cfg.scales)

    def wait_for_screen(self, name: str, timeout: float | None = None) -> np.ndarray | None:
        end = self.clock() + (timeout if timeout is not None else self.cfg.screen_timeout)
        while True:
            img = self.grab()
            if self.identify(img) == name:
                return img
            if self.clock() >= end:
                return None
            self.sleep(self.cfg.poll)

    # ---- run -------------------------------------------------------------
    def run(self) -> None:
        s = self.script
        ref = (s.ref_width, s.ref_height, s.ref_dpi)
        forced = False
        info = self.dev.screen_info()
        if (info.width, info.height, info.dpi) != ref:
            if self.cfg.force_size:
                self.dev.set_screen(*ref)
                forced = True
                info = self.dev.screen_info()
            if (info.width, info.height, info.dpi) != ref:
                self._letterbox = True  # cannot force: normalise keeping aspect ratio
        self._expected = (info.width, info.height, info.dpi)
        try:
            for step in s.steps:
                while self.paused:
                    self.sleep(self.cfg.poll)
                    self._still_since = self.clock()  # a pause is not a frozen screen
                self.run_step(step)
        finally:
            if forced:
                self.dev.reset_screen()

    def run_step(self, step: Step) -> None:
        t0 = self.clock()
        img = self.grab()
        if step.from_screen and self.identify(img) != step.from_screen:
            img = self.wait_for_screen(step.from_screen)
            if img is None:
                img = self.grab()
                if not self.hooks.recover(self, step, img):
                    self._fail(step, f"not on screen {step.from_screen}")
                img = self.wait_for_screen(step.from_screen) or self.grab()
        for attempt in range(self.cfg.retries + 1):
            if self._perform(step, img):
                break
            if attempt == self.cfg.retries:
                if not self.hooks.recover(self, step, img):
                    self._fail(step, "target not found")
                if not self._perform(step, self.grab()):
                    self._fail(step, "target not found")
                break
            self.sleep(self.cfg.poll)
            img = self.grab()
        self.sleep(step.wait_ms / 1000)
        if step.to_screen and self.wait_for_screen(step.to_screen) is None:
            self.hooks.record(step, False, step.wait_ms)
            self._fail(step, f"did not reach screen {step.to_screen}")
        self.hooks.record(step, True, int((self.clock() - t0) * 1000))

    def _fail(self, step: Step, reason: str):
        try:
            shot = self.dev.screencap()
        except Exception:
            shot = None
        self.hooks.record(step, False, step.wait_ms)
        raise StepFailed(step, reason, shot)

    # ---- actions ---------------------------------------------------------
    def _jit(self, x: int, y: int) -> tuple[int, int]:
        j = self.cfg.jitter_px
        return x + self.rng.randint(-j, j), y + self.rng.randint(-j, j)

    def locate(self, step: Step, img: np.ndarray) -> tuple[int, int] | None:
        """Tap target in real device pixels: template (all variants) first, point if no template."""
        s = self.script
        if step.template:
            for name in self.hooks.variants(step):
                t = self.assets.load(name)
                if t is None:
                    continue
                m = find_template(img, t, step.threshold, self.cfg.scales)
                if m:
                    self.hooks.on_match(step, img, m.x, m.y, m.scale)
                    return self._real(m.x, m.y)
            return None
        if step.point:
            return self._real(*step.point.to_px(s.ref_width, s.ref_height, s.ref_dpi))
        return None

    def _perform(self, step: Step, img: np.ndarray) -> bool:
        d, a = self.dev, step.action
        if a == "tap":
            pos = self.locate(step, img)
            if pos is None:
                return False
            d.tap(*self._jit(*pos))
        elif a == "swipe" and step.point and step.point2:
            s = self.script
            p1 = self._real(*step.point.to_px(s.ref_width, s.ref_height, s.ref_dpi))
            p2 = self._real(*step.point2.to_px(s.ref_width, s.ref_height, s.ref_dpi))
            d.swipe(*self._jit(*p1), *self._jit(*p2), int(step.value or 300))
        elif a == "key":
            d.key(step.value)
        elif a == "text":
            d.text(self._resolve(step.value or ""))
        elif a == "start_app":
            d.start_app(step.value or "")
        elif a == "stop_app":
            d.stop_app(step.value or "")
        elif a == "wait":
            pass
        return True

    def _resolve(self, value: str) -> str:
        if value.startswith("{") and value.endswith("}") and self.cfg.secrets:
            return self.cfg.secrets(value[1:-1])
        return value
