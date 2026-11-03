from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

Region = tuple[float, float, float, float]  # x0, y0, x1, y1 as fractions of the image

DEFAULT_SCALES = (1.0, 0.95, 1.05, 0.9, 1.1, 0.8, 1.2)


@dataclass(frozen=True)
class Match:
    x: int  # center, full-image pixels
    y: int
    w: int
    h: int
    score: float
    scale: float = 1.0


def decode(png: bytes) -> np.ndarray:
    img = cv2.imdecode(np.frombuffer(png, np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("invalid image data")
    return img


def encode(img: np.ndarray) -> bytes:
    ok, buf = cv2.imencode(".png", img)
    if not ok:
        raise ValueError("cannot encode image")
    return buf.tobytes()


def find_template(
    screen: np.ndarray,
    tmpl: np.ndarray,
    threshold: float = 0.85,
    scales: tuple[float, ...] = (1.0,),
    region: Region | None = None,
) -> Match | None:
    """Best template match with score >= threshold, trying `scales` in order (early exit)."""
    H, W = screen.shape[:2]
    x0, y0 = 0, 0
    area = screen
    if region:
        x0, y0 = int(region[0] * W), int(region[1] * H)
        area = screen[y0 : int(region[3] * H), x0 : int(region[2] * W)]
    best: Match | None = None
    for s in scales:
        t = tmpl if s == 1.0 else cv2.resize(tmpl, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
        th, tw = t.shape[:2]
        if th > area.shape[0] or tw > area.shape[1] or th < 4 or tw < 4:
            continue
        res = cv2.matchTemplate(area, t, cv2.TM_CCOEFF_NORMED)
        _, score, _, loc = cv2.minMaxLoc(res)
        if best is None or score > best.score:
            best = Match(x0 + loc[0] + tw // 2, y0 + loc[1] + th // 2, tw, th, float(score), s)
        if score >= threshold:
            break
    return best if best and best.score >= threshold else None


def identify_screen(
    screen: np.ndarray,
    fingerprints: dict[str, list[np.ndarray]],
    threshold: float = 0.85,
    scales: tuple[float, ...] = (1.0,),
) -> str | None:
    """Name of the screen whose templates ALL match; ties go to the highest mean score."""
    best_name, best_score = None, 0.0
    for name, tmpls in fingerprints.items():
        if not tmpls:
            continue
        scores = []
        for t in tmpls:
            m = find_template(screen, t, threshold, scales)
            if m is None:
                break
            scores.append(m.score)
        else:
            mean = sum(scores) / len(scores)
            if mean > best_score:
                best_name, best_score = name, mean
    return best_name


def letterbox(img: np.ndarray, w: int, h: int) -> tuple[np.ndarray, float, int, int]:
    """Fit img into w*h keeping aspect ratio. Returns (image, scale, off_x, off_y)."""
    ih, iw = img.shape[:2]
    s = min(w / iw, h / ih)
    nw, nh = max(1, round(iw * s)), max(1, round(ih * s))
    resized = cv2.resize(img, (nw, nh), interpolation=cv2.INTER_AREA)
    canvas = np.zeros((h, w, 3), np.uint8)
    ox, oy = (w - nw) // 2, (h - nh) // 2
    canvas[oy : oy + nh, ox : ox + nw] = resized
    return canvas, s, ox, oy
