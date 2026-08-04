from __future__ import annotations

import numpy as np

from app.vision.template_match import TemplateMatcher


def checkerboard(size: int = 20) -> np.ndarray:
    block = np.zeros((size, size, 3), dtype=np.uint8)
    block[::2] = 200
    block[:, 1::2] = 200
    return block


def test_match_finds_template() -> None:
    template = checkerboard()
    source = np.zeros((60, 80, 3), dtype=np.uint8)
    source[15:35, 20:40] = template

    result = TemplateMatcher().match(source, template, threshold=0.9)

    assert result is not None
    assert result.box == (20, 15, 20, 20)
    assert result.center == (30, 25)
    assert result.confidence >= 0.9


def test_match_returns_none_below_threshold() -> None:
    source = np.zeros((60, 80, 3), dtype=np.uint8)
    template = checkerboard()

    result = TemplateMatcher().match(source, template, threshold=0.9)

    assert result is None


def test_match_returns_none_when_template_larger() -> None:
    source = np.zeros((10, 10, 3), dtype=np.uint8)
    template = checkerboard(20)

    result = TemplateMatcher().match(source, template)

    assert result is None


def test_find_all_locates_multiple_matches() -> None:
    template = checkerboard(10)
    source = np.zeros((60, 120, 3), dtype=np.uint8)
    source[10:20, 10:20] = template
    source[30:40, 60:70] = template

    results = TemplateMatcher().find_all(source, template, threshold=0.9)

    assert len(results) == 2


def test_match_accepts_grayscale_frame() -> None:
    template_gray = np.zeros((20, 20), dtype=np.uint8)
    template_gray[::2] = 200
    template_gray[:, 1::2] = 200

    source = np.zeros((60, 80), dtype=np.uint8)
    source[15:35, 20:40] = template_gray

    result = TemplateMatcher().match(source, template_gray, threshold=0.9)

    assert result is not None
