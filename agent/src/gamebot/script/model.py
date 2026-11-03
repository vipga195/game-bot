from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Action = Literal["tap", "swipe", "key", "text", "wait", "start_app", "stop_app"]


class Point(BaseModel):
    """Resolution-independent coordinate.

    ax/ay = 'c': x/y is a fraction of width/height. ax='l'/'r' (ay='t'/'b'): x/y is a dp offset
    from that edge, so HUD elements stay put when the aspect ratio changes.
    """

    x: float
    y: float
    ax: Literal["l", "c", "r"] = "c"
    ay: Literal["t", "c", "b"] = "c"

    @classmethod
    def from_px(cls, px: int, py: int, w: int, h: int, dpi: int, ax="c", ay="c") -> Point:
        dp = 160 / dpi
        x = px / w if ax == "c" else (px if ax == "l" else w - px) * dp
        y = py / h if ay == "c" else (py if ay == "t" else h - py) * dp
        return cls(x=x, y=y, ax=ax, ay=ay)

    def to_px(self, w: int, h: int, dpi: int) -> tuple[int, int]:
        px_per_dp = dpi / 160
        x = self.x * w if self.ax == "c" else self.x * px_per_dp
        y = self.y * h if self.ay == "c" else self.y * px_per_dp
        if self.ax == "r":
            x = w - x
        if self.ay == "b":
            y = h - y
        return round(x), round(y)


class Step(BaseModel):
    id: str
    action: Action
    from_screen: str | None = None  # expected screen before the step
    to_screen: str | None = None  # expected screen after the step
    template: str | None = None  # asset name; target is located by image when present
    point: Point | None = None  # fallback / direct coordinate
    point2: Point | None = None  # swipe end
    value: str | None = None  # key code, literal text, package, or "{username}"/"{password}"
    wait_ms: int = 800
    threshold: float = 0.85


class Script(BaseModel):
    id: str
    game_id: str
    mode: str = "task"  # task | train | event | login
    ref_width: int
    ref_height: int
    ref_dpi: int
    screens: dict[str, list[str]] = Field(default_factory=dict)  # screen name -> fingerprint assets
    steps: list[Step] = Field(default_factory=list)
