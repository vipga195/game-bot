from __future__ import annotations

from pathlib import Path

import numpy as np

from ..vision import decode, encode


class AssetStore:
    """Template images stored as PNG files under <root>/<script_id>/."""

    def __init__(self, root: str | Path, script_id: str):
        self.dir = Path(root) / script_id
        self.dir.mkdir(parents=True, exist_ok=True)

    def save(self, name: str, img: np.ndarray) -> None:
        (self.dir / f"{name}.png").write_bytes(encode(img))

    def load(self, name: str) -> np.ndarray | None:
        p = self.dir / f"{name}.png"
        return decode(p.read_bytes()) if p.exists() else None

    def delete(self, name: str) -> None:
        (self.dir / f"{name}.png").unlink(missing_ok=True)

    def names(self, prefix: str = "") -> list[str]:
        return sorted(p.stem for p in self.dir.glob(f"{prefix}*.png"))

    def crop(self, name: str, screen: np.ndarray, cx: int, cy: int, size: int = 120) -> None:
        H, W = screen.shape[:2]
        half = size // 2
        x0, y0 = max(0, min(cx - half, W - size)), max(0, min(cy - half, H - size))
        self.save(name, screen[y0 : y0 + size, x0 : x0 + size])

    def crop_region(
        self, name: str, screen: np.ndarray, region: tuple[float, float, float, float]
    ) -> None:
        H, W = screen.shape[:2]
        x0, y0 = int(region[0] * W), int(region[1] * H)
        x1, y1 = int(region[2] * W), int(region[3] * H)
        self.save(name, screen[y0:y1, x0:x1])
