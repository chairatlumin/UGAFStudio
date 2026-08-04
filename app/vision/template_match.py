from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np


@dataclass(frozen=True)
class MatchResult:
    """Location and confidence of a template match."""

    x: int
    y: int
    width: int
    height: int
    confidence: float

    @property
    def center(self) -> tuple[int, int]:
        """Return the center of the matched region."""
        return self.x + self.width // 2, self.y + self.height // 2

    @property
    def box(self) -> tuple[int, int, int, int]:
        """Return the bounding box as x, y, width, height."""
        return self.x, self.y, self.width, self.height


class TemplateMatcher:
    """Finds a template image inside a captured frame."""

    def match(
        self,
        source: np.ndarray,
        template: np.ndarray,
        threshold: float = 0.9,
    ) -> MatchResult | None:
        """
        Return the best template match above the confidence threshold.

        Args:
            source: Frame to search, BGR or BGRA image.
            template: Pattern to locate, BGR or BGRA image.
            threshold: Minimum confidence between 0.0 and 1.0.

        Returns:
            Best MatchResult or None if no match meets the threshold.
        """
        if template.shape[0] > source.shape[0] or template.shape[1] > source.shape[1]:
            return None

        source_gray = _to_gray(source)
        template_gray = _to_gray(template)

        result = _correlate(source_gray, template_gray)
        _, max_value, _, max_location = cv2.minMaxLoc(result)

        if max_value < threshold:
            return None

        height, width = template.shape[:2]
        x, y = max_location

        return MatchResult(x=x, y=y, width=width, height=height, confidence=float(max_value))

    def find_all(
        self,
        source: np.ndarray,
        template: np.ndarray,
        threshold: float = 0.9,
    ) -> list[MatchResult]:
        """
        Return all template matches above the confidence threshold.

        Overlapping detections are suppressed to keep the strongest match.
        """
        source_gray = _to_gray(source)
        template_gray = _to_gray(template)

        height, width = template.shape[:2]

        result = _correlate(source_gray, template_gray)
        locations = np.where(result >= threshold)

        matches: list[MatchResult] = []

        for y, x in zip(*locations, strict=False):
            overlaps = [
                match for match in matches if abs(match.x - x) < width and abs(match.y - y) < height
            ]

            if overlaps:
                continue

            matches.append(
                MatchResult(
                    x=int(x),
                    y=int(y),
                    width=width,
                    height=height,
                    confidence=float(result[y, x]),
                )
            )

        return matches


def _to_gray(frame: np.ndarray) -> np.ndarray:
    if frame.ndim == 2:
        return frame

    return cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)


def _correlate(source: np.ndarray, template: np.ndarray) -> np.ndarray:
    result = cv2.matchTemplate(source, template, cv2.TM_CCOEFF_NORMED)
    return np.nan_to_num(result, nan=0.0, posinf=0.0, neginf=0.0)
