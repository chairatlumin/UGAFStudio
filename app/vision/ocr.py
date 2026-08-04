from __future__ import annotations

import shutil
from dataclasses import dataclass
from typing import Any

import cv2
import numpy as np

from app.vision.template_match import MatchResult


@dataclass(frozen=True)
class OCRWord:
    """A word detected by the OCR engine."""

    text: str
    box: MatchResult
    confidence: float

    @property
    def center(self) -> tuple[int, int]:
        return self.box.center


class OCREngine:
    """Optical character recognition backed by pytesseract.

    The engine degrades gracefully when the Tesseract binary is unavailable.
    """

    def __init__(self, tesseract_cmd: str | None = None) -> None:
        self._tesseract_cmd = tesseract_cmd
        self._pytesseract: Any = None

    def available(self) -> bool:
        """Return whether Tesseract is installed and importable."""
        if self._pytesseract is None:
            try:
                import pytesseract

                if self._tesseract_cmd:
                    pytesseract.pytesseract.tesseract_cmd = self._tesseract_cmd

                self._pytesseract = pytesseract
            except ImportError:
                return False

        return shutil.which(self._tesseract_cmd or "tesseract") is not None

    def read(self, frame: np.ndarray) -> str:
        """Return the raw text recognized in a BGR or BGRA frame."""
        if not self.available():
            return ""

        text = self._pytesseract.image_to_string(_to_rgb(frame))

        return str(text)

    def read_words(self, frame: np.ndarray) -> list[OCRWord]:
        """Return recognized words with their locations and confidence."""
        if not self.available():
            return []

        data = self._pytesseract.image_to_data(_to_rgb(frame), output_type="dict")

        words: list[OCRWord] = []

        for index, text in enumerate(data["text"]):
            word = str(text).strip()

            if not word:
                continue

            confidence = float(data["conf"][index])

            if confidence < 0:
                continue

            box = MatchResult(
                x=int(data["left"][index]),
                y=int(data["top"][index]),
                width=int(data["width"][index]),
                height=int(data["height"][index]),
                confidence=confidence / 100.0,
            )

            words.append(OCRWord(text=word, box=box, confidence=confidence / 100.0))

        return words


def _to_rgb(frame: np.ndarray) -> np.ndarray:
    if frame.ndim == 2:
        return frame

    if frame.shape[2] == 4:
        return cv2.cvtColor(frame, cv2.COLOR_BGRA2RGB)

    return cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
