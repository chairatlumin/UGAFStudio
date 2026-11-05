from __future__ import annotations

import numpy as np
import pytest

from app.vision.ocr import DEFAULT_TESSERACT_CMD
from qa_framework.gameplay.assertions import VisualAssertionEngine


class FakeOCR:
    """Stand-in OCR engine returning fixed words/regions, no Tesseract needed."""

    def __init__(self, words: list[tuple[str, tuple[int, int, int, int], float]]) -> None:
        # words: (text, (x, y, w, h), confidence 0-1)
        self._words = words
        self._regions: list[np.ndarray] = []

    def available(self) -> bool:
        return True

    def read(
        self, frame, *, scale=1.0, psm=None, lang="eng", config="", region=None, preprocessing=None
    ) -> str:  # noqa: ANN001
        return " ".join(w[0] for w in self._words)

    def read_words(
        self,
        frame,
        *,
        scale=1.0,
        lang="eng",
        config="",
        psm=None,
        region=None,
        preprocessing=None,
        confidence_threshold=0.0,
    ) -> list:  # noqa: ANN001, C901
        from app.vision.ocr import OCRWord
        from app.vision.template_match import MatchResult

        self._regions.append(region)
        out = []
        for text, box, conf in self._words:
            if conf < confidence_threshold:
                continue
            x, y, w, h = box
            out.append(
                OCRWord(
                    text=text,
                    box=MatchResult(x=x, y=y, width=w, height=h, confidence=conf),
                    confidence=conf,
                )
            )
        return out


def _color_frame(bgr: tuple[int, int, int]) -> np.ndarray:
    return np.full((100, 100, 3), bgr, dtype=np.uint8)


def test_ocr_word_present_passes_on_match() -> None:
    engine = VisualAssertionEngine(ocr_engine=FakeOCR([("PLAY", (10, 10, 40, 20), 0.95)]))
    res = engine.assert_frame(
        _color_frame((0, 0, 0)),
        [
            {
                "name": "play btn",
                "check": "ocr_word_present",
                "text": "PLAY",
                "confidence_threshold": 0.6,
            }
        ],
    )
    assert res[0].passed
    assert "PLAY" in res[0].message


def test_ocr_word_present_fails_below_confidence() -> None:
    engine = VisualAssertionEngine(ocr_engine=FakeOCR([("PLAY", (10, 10, 40, 20), 0.30)]))
    res = engine.assert_frame(
        _color_frame((0, 0, 0)),
        [
            {
                "name": "play btn",
                "check": "ocr_word_present",
                "text": "PLAY",
                "confidence_threshold": 0.6,
            }
        ],
    )
    assert not res[0].passed


def test_ocr_word_present_case_insensitive() -> None:
    engine = VisualAssertionEngine(ocr_engine=FakeOCR([("Settings", (10, 10, 40, 20), 0.9)]))
    res = engine.assert_frame(
        _color_frame((0, 0, 0)),
        [
            {
                "name": "settings",
                "check": "ocr_word_present",
                "text": "settings",
                "confidence_threshold": 0.5,
            }
        ],
    )
    assert res[0].passed


def test_ocr_region_contains_crops_correctly() -> None:
    ocr = FakeOCR([("GRAPHICS", (10, 10, 60, 20), 0.9)])
    engine = VisualAssertionEngine(ocr_engine=ocr)
    engine.assert_frame(
        _color_frame((0, 0, 0)),
        [
            {
                "name": "gfx",
                "check": "ocr_region_contains",
                "text": "GRAPHICS",
                "region": [0, 0, 50, 50],
            }
        ],
    )
    # the region was passed down to OCR
    assert ocr._regions[-1] == (0, 0, 50, 50)


def test_ocr_region_contains_missing_region_raises() -> None:
    engine = VisualAssertionEngine(ocr_engine=FakeOCR([("X", (1, 1, 4, 4), 0.9)]))
    res = engine.assert_frame(
        _color_frame((0, 0, 0)),
        [{"name": "gfx", "check": "ocr_region_contains", "text": "GRAPHICS"}],
    )
    assert not res[0].passed
    assert "region" in res[0].message


def test_color_region_detected_constrains_to_region() -> None:
    frame = _color_frame((20, 20, 200))
    # paint a single red pixel outside the region so a full-frame check would differ
    frame[80, 80] = (200, 20, 20)
    res = VisualAssertionEngine().assert_frame(
        frame,
        [
            {
                "name": "red hud",
                "check": "color_region_detected",
                "color": [200, 20, 20],
                "region": [70, 70, 20, 20],
                "tolerance": 30,
            }
        ],
    )
    assert res[0].passed


def test_color_region_detected_absent_in_region() -> None:
    frame = _color_frame((20, 20, 200))
    res = VisualAssertionEngine().assert_frame(
        frame,
        [
            {
                "name": "red hud",
                "check": "color_region_detected",
                "color": [200, 20, 20],
                "region": [0, 0, 20, 20],
                "tolerance": 30,
            }
        ],
    )
    assert not res[0].passed


def test_frame_not_black_detects_visible_frame() -> None:
    frame = np.zeros((100, 100, 3), dtype=np.uint8)
    frame[20:80, 20:80] = (60, 55, 48)
    result = VisualAssertionEngine().assert_frame(
        frame,
        [{"name": "video frame", "check": "frame_not_black", "min_visible_ratio": 0.2}],
    )
    assert result[0].passed
    assert "Visible pixel ratio" in result[0].message


def test_frame_not_black_rejects_black_frame() -> None:
    result = VisualAssertionEngine().assert_frame(
        np.zeros((100, 100, 3), dtype=np.uint8),
        [{"name": "video frame", "check": "frame_not_black"}],
    )
    assert not result[0].passed
    assert "Near-black frame" in result[0].message


def test_frame_not_black_respects_visible_ratio_threshold() -> None:
    frame = np.zeros((100, 100, 3), dtype=np.uint8)
    frame[0:10, 0:10] = (80, 80, 80)
    result = VisualAssertionEngine().assert_frame(
        frame,
        [{"name": "video frame", "check": "frame_not_black", "min_visible_ratio": 0.2}],
    )
    assert not result[0].passed


def test_frame_not_black_rejects_out_of_range_threshold() -> None:
    result = VisualAssertionEngine().assert_frame(
        np.zeros((10, 10, 3), dtype=np.uint8),
        [{"name": "video frame", "check": "frame_not_black", "min_visible_ratio": 2}],
    )
    assert not result[0].passed
    assert "between 0 and 1" in result[0].message


def test_assertion_engine_dispatch_new_types() -> None:
    engine = VisualAssertionEngine(ocr_engine=FakeOCR([("EXIT", (1, 1, 20, 10), 0.9)]))
    results = engine.assert_frame(
        _color_frame((0, 0, 0)),
        [
            {"name": "a", "check": "ocr_word_present", "text": "EXIT"},
            {"name": "b", "check": "ocr_region_contains", "text": "EXIT", "region": [0, 0, 10, 10]},
            {
                "name": "c",
                "check": "color_region_detected",
                "color": [0, 0, 0],
                "region": [0, 0, 10, 10],
            },
        ],
    )
    assert all(r.passed for r in results)


def test_ocr_contains_respects_preprocessing() -> None:
    engine = VisualAssertionEngine(ocr_engine=FakeOCR([("Tutorial", (1, 1, 40, 10), 0.9)]))
    res = engine.assert_frame(
        _color_frame((0, 0, 0)),
        [
            {
                "name": "tut",
                "check": "ocr_contains",
                "text": "tutorial",
                "preprocessing": "ui",
                "region": [0, 0, 20, 20],
            }
        ],
    )
    assert res[0].passed


def test_unsupported_check_raises() -> None:
    res = VisualAssertionEngine().assert_frame(
        _color_frame((0, 0, 0)),
        [{"name": "x", "check": "bogus", "text": "y"}],
    )
    assert not res[0].passed
    assert "Unsupported" in res[0].message


@pytest.mark.skipif(
    not __import__("pathlib").Path(DEFAULT_TESSERACT_CMD).is_file(),
    reason="Tesseract not installed",
)
def test_ocr_word_present_live_tesseract() -> None:
    from app.vision.ocr import OCREngine

    img = np.zeros((60, 300, 3), dtype=np.uint8)
    import cv2

    cv2.putText(img, "START", (10, 40), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 255, 255), 2)
    engine = VisualAssertionEngine(ocr_engine=OCREngine())
    res = engine.assert_frame(
        img,
        [
            {
                "name": "start",
                "check": "ocr_word_present",
                "text": "START",
                "preprocessing": "binary",
                "confidence_threshold": 0.4,
            }
        ],
    )
    assert res[0].passed
