from __future__ import annotations

import numpy as np

from app.vision.color_detector import ColorDetector, DetectionResult
from app.vision.ocr import OCREngine
from app.vision.template_match import MatchResult, TemplateMatcher


class ObjectDetector:
    """High-level vision service combining template, color, and OCR."""

    def __init__(
        self,
        matcher: TemplateMatcher | None = None,
        color_detector: ColorDetector | None = None,
        ocr: OCREngine | None = None,
    ) -> None:
        self.matcher = matcher if matcher is not None else TemplateMatcher()
        self.color_detector = color_detector if color_detector is not None else ColorDetector()
        self.ocr = ocr if ocr is not None else OCREngine()

    def find_template(
        self,
        frame: np.ndarray,
        template: np.ndarray,
        threshold: float = 0.9,
    ) -> MatchResult | None:
        """Locate a template image inside a frame."""
        return self.matcher.match(frame, template, threshold)

    def find_color(
        self,
        frame: np.ndarray,
        target: tuple[int, int, int],
        tolerance: int = 30,
    ) -> DetectionResult | None:
        """Locate the largest region matching a BGR color."""
        return self.color_detector.detect(frame, target, tolerance)

    def read_text(self, frame: np.ndarray) -> str:
        """Recognize text inside a frame."""
        return self.ocr.read(frame)
