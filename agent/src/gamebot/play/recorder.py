from __future__ import annotations

import time
from collections.abc import Callable

from ..script import AssetStore, Point, Script, Step
from ..vision import decode


class Recorder:
    """Turns user-driven actions into a state-graph script.

    The UI shows the live screen; the user clicks on it and the agent both executes the action
    on the device and records it (screenshot before -> template crop around the target).
    """

    def __init__(
        self,
        device,
        assets: AssetStore,
        script_id: str,
        game_id: str,
        mode: str = "task",
        sleep: Callable[[float], None] = time.sleep,
    ):
        info = device.screen_info()
        self.dev, self.assets, self.sleep = device, assets, sleep
        self.info = info
        self.script = Script(
            id=script_id,
            game_id=game_id,
            mode=mode,
            ref_width=info.width,
            ref_height=info.height,
            ref_dpi=info.dpi,
        )

    def _pt(self, x: int, y: int, ax="c", ay="c") -> Point:
        i = self.info
        return Point.from_px(x, y, i.width, i.height, i.dpi, ax, ay)

    def _add(self, **kw) -> Step:
        step = Step(id=f"s{len(self.script.steps) + 1}", **kw)
        self.script.steps.append(step)
        return step

    def mark_screen(self, name: str, region=(0.0, 0.0, 1.0, 1.0)) -> None:
        """Save the current screen region as a fingerprint of screen `name`."""
        img = decode(self.dev.screencap())
        idx = len(self.script.screens.get(name, []))
        asset = f"screen_{name}_{idx}"
        self.assets.crop_region(asset, img, region)
        self.script.screens.setdefault(name, []).append(asset)

    def record_tap(self, x: int, y: int, from_screen=None, to_screen=None, ax="c", ay="c") -> Step:
        img = decode(self.dev.screencap())
        step_id = f"s{len(self.script.steps) + 1}"
        self.assets.crop(f"{step_id}_tpl", img, x, y)
        self.dev.tap(x, y)
        self.sleep(0.8)
        return self._add(
            action="tap",
            template=f"{step_id}_tpl",
            point=self._pt(x, y, ax, ay),
            from_screen=from_screen,
            to_screen=to_screen,
        )

    def record_swipe(self, x1, y1, x2, y2, ms=300, from_screen=None, to_screen=None) -> Step:
        self.dev.swipe(x1, y1, x2, y2, ms)
        self.sleep(0.8)
        return self._add(
            action="swipe",
            point=self._pt(x1, y1),
            point2=self._pt(x2, y2),
            value=str(ms),
            from_screen=from_screen,
            to_screen=to_screen,
        )

    def record_key(self, keycode, from_screen=None, to_screen=None) -> Step:
        self.dev.key(keycode)
        self.sleep(0.5)
        return self._add(
            action="key", value=str(keycode), from_screen=from_screen, to_screen=to_screen
        )

    def record_text(self, value: str, from_screen=None, to_screen=None) -> Step:
        """`value` may be a placeholder like "{username}" so secrets never enter the script."""
        if not (value.startswith("{") and value.endswith("}")):
            self.dev.text(value)
        return self._add(action="text", value=value, from_screen=from_screen, to_screen=to_screen)

    def finish(self) -> Script:
        return self.script
