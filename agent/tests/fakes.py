from __future__ import annotations

import numpy as np

from gamebot.device import ScreenInfo
from gamebot.vision import encode

W, H = 360, 640


def noise(seed: int, w: int, h: int) -> np.ndarray:
    return np.random.default_rng(seed).integers(0, 255, (h, w, 3), dtype=np.uint8)


def make_screen(seed: int, title_seed: int, button=None, size=(W, H)) -> np.ndarray:
    """Noise background + title patch at top + optional button patch (x, y, w, h, seed)."""
    img = noise(seed, *size)
    img[20:80, 100:260] = noise(title_seed, 160, 60)
    if button:
        x, y, w, h, bs = button
        img[y : y + h, x : x + w] = noise(bs, w, h)
    return img


class FakeDevice:
    """Screens + button regions -> next screen. Records taps and screen changes."""

    def __init__(self, screens: dict[str, np.ndarray], buttons: dict[str, tuple], start: str):
        self.screens, self.buttons, self.cur = screens, buttons, start
        self.taps: list[tuple[int, int]] = []
        self.keys: list = []
        self.texts: list[str] = []
        self.info = ScreenInfo(W, H, 160)
        self.physical = ScreenInfo(W, H, 160)
        self.overridden = False
        self.on_screencap = None

    def screencap(self) -> bytes:
        if self.on_screencap:
            self.on_screencap(self)
        return encode(self.screens[self.cur])

    def screen_info(self):
        return self.info

    def set_screen(self, w, h, dpi):
        self.info, self.overridden = ScreenInfo(w, h, dpi), True

    def reset_screen(self):
        self.info, self.overridden = self.physical, False

    def tap(self, x, y):
        self.taps.append((x, y))
        b = self.buttons.get(self.cur)
        if b and b[0] <= x < b[0] + b[2] and b[1] <= y < b[1] + b[3]:
            self.cur = b[5]

    def swipe(self, *a):
        pass

    def key(self, k):
        self.keys.append(k)

    def text(self, t):
        self.texts.append(t)

    def start_app(self, p):
        pass

    def stop_app(self, p):
        pass


def two_screen_game() -> FakeDevice:
    """login --[button]--> main"""
    login = make_screen(1, 11, (120, 300, 120, 50, 21))
    main = make_screen(2, 12)
    return FakeDevice(
        {"login": login, "main": main},
        {"login": (120, 300, 120, 50, 21, "main")},
        "login",
    )
