from __future__ import annotations

import re
from typing import Protocol

import numpy as np


class OcrEngine(Protocol):
    def read(self, img: np.ndarray) -> str: ...


class RapidOcr:
    """RapidOCR wrapper; the dependency is optional and imported lazily."""

    def __init__(self) -> None:
        self._eng = None

    def read(self, img: np.ndarray) -> str:
        if self._eng is None:
            from rapidocr_onnxruntime import RapidOCR  # type: ignore[import-not-found]

            self._eng = RapidOCR()
        result, _ = self._eng(img)
        return " ".join(r[1] for r in (result or []))


_HMS = re.compile(r"(\d{1,3})\s*[:：]\s*(\d{2})(?:\s*[:：]\s*(\d{2}))?")
_UNITS = re.compile(r"(\d+)\s*(?:d|ngay|ngày)|(\d+)\s*(?:h|giờ|gio)|(\d+)\s*(?:m|phút|phut)", re.I)


def parse_countdown(text: str) -> int | None:
    """'02:15:00' -> 8100, '15:30' -> 930 (mm:ss), '2h 15m' -> 8100. None if unparsable."""
    m = _HMS.search(text)
    if m:
        a, b, c = int(m.group(1)), int(m.group(2)), m.group(3)
        return a * 3600 + b * 60 + int(c) if c is not None else a * 60 + b
    total, found = 0, False
    for m in _UNITS.finditer(text):
        found = True
        if m.group(1):
            total += int(m.group(1)) * 86400
        elif m.group(2):
            total += int(m.group(2)) * 3600
        else:
            total += int(m.group(3)) * 60
    return total if found else None
