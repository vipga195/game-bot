import cv2
import numpy as np
import pytest
from pytest import approx as pytest_approx

from gamebot.vision import find_template, identify_screen, letterbox, parse_countdown

from .fakes import make_screen, noise


def test_template_exact_and_threshold():
    scr = make_screen(1, 11, (120, 300, 120, 50, 21))
    tpl = noise(21, 120, 50)
    m = find_template(scr, tpl)
    assert m and abs(m.x - 180) <= 1 and abs(m.y - 325) <= 1
    assert find_template(scr, noise(99, 120, 50)) is None


def test_template_multiscale():
    base = cv2.resize(noise(7, 10, 5), (120, 50), interpolation=cv2.INTER_NEAREST)  # blocky
    scr = make_screen(1, 11)
    scr[300:350, 120:240] = base
    big = cv2.resize(base, None, fx=1.1, fy=1.1, interpolation=cv2.INTER_NEAREST)
    m = find_template(scr, big, threshold=0.9, scales=(1.0, 0.95, 0.9))
    assert m and m.scale == pytest_approx(0.9)


def test_identify_screen():
    a, b = make_screen(1, 11), make_screen(2, 12)
    fps = {"a": [a[20:80, 100:260]], "b": [b[20:80, 100:260]]}
    assert identify_screen(a, fps) == "a"
    assert identify_screen(noise(5, 360, 640), fps) is None


def test_letterbox_keeps_aspect():
    img = noise(1, 200, 100)
    out, s, ox, oy = letterbox(img, 100, 100)
    assert out.shape[:2] == (100, 100) and s == 0.5 and ox == 0 and oy == 25


def test_countdown():
    assert parse_countdown("còn 02:15:00") == 8100
    assert parse_countdown("15:30") == 930
    assert parse_countdown("2h 15m") == 8100
    assert parse_countdown("abc") is None


def test_rapidocr_reads_real_image():
    pytest.importorskip("rapidocr_onnxruntime")
    from gamebot.vision.ocr import RapidOcr, parse_countdown

    img = np.full((120, 480, 3), 255, np.uint8)
    cv2.putText(img, "Ready in 02:15:00", (10, 70), cv2.FONT_HERSHEY_SIMPLEX, 1.4, (0, 0, 0), 3)
    assert parse_countdown(RapidOcr().read(img)) == 8100
