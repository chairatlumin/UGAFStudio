from __future__ import annotations

import numpy as np

from app.vision.color_detector import ColorDetector


def test_detect_finds_largest_matching_region() -> None:
    frame = np.zeros((100, 100, 3), dtype=np.uint8)
    frame[10:30, 20:40] = [200, 100, 50]
    frame[60:70, 60:70] = [200, 100, 50]

    result = ColorDetector().detect(frame, target=(200, 100, 50))

    assert result is not None
    assert result.width == 20
    assert result.height == 20
    assert result.center == (30, 20)


def test_detect_returns_none_when_color_absent() -> None:
    frame = np.zeros((50, 50, 3), dtype=np.uint8)

    result = ColorDetector().detect(frame, target=(200, 100, 50))

    assert result is None


def test_detect_accepts_bgra_frame() -> None:
    frame = np.zeros((50, 50, 4), dtype=np.uint8)
    frame[:, :, :3] = [200, 100, 50]
    frame[:, :, 3] = 255

    result = ColorDetector().detect(frame, target=(200, 100, 50))

    assert result is not None
    assert result.area > 0
