from __future__ import annotations

import numpy as np

from app.vision.ocr import OCREngine, OCRWord


class FakePytesseract:
    tesseract_cmd = None

    def image_to_string(self, image: np.ndarray) -> str:
        return "HELLO WORLD"

    def image_to_data(self, image: np.ndarray, output_type: str) -> dict[str, list]:
        return {
            "text": ["HELLO", "WORLD", ""],
            "conf": [95, 88, -1],
            "left": [0, 100, 0],
            "top": [0, 0, 0],
            "width": [50, 50, 0],
            "height": [20, 20, 0],
        }


class FakeAvailableOCREngine(OCREngine):
    def available(self) -> bool:
        return True


def make_engine() -> FakeAvailableOCREngine:
    engine = FakeAvailableOCREngine()
    engine._pytesseract = FakePytesseract()
    return engine


def test_read_returns_recognized_text() -> None:
    frame = np.zeros((30, 200, 3), dtype=np.uint8)

    assert make_engine().read(frame) == "HELLO WORLD"


def test_read_words_filters_blanks_and_low_confidence() -> None:
    frame = np.zeros((30, 200, 3), dtype=np.uint8)

    words = make_engine().read_words(frame)

    assert len(words) == 2
    assert all(isinstance(word, OCRWord) for word in words)
    assert words[0].text == "HELLO"
    assert words[0].center == (25, 10)
    assert words[0].confidence == 0.95


def test_unavailable_engine_returns_empty() -> None:
    frame = np.zeros((30, 200, 3), dtype=np.uint8)

    assert OCREngine().read(frame) == ""
    assert OCREngine().read_words(frame) == []
