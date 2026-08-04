from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np


@dataclass(frozen=True)
class DetectionResult:
    """Bounding box of a detected object."""

    x: int
    y: int
    width: int
    height: int
    area: int

    @property
    def center(self) -> tuple[int, int]:
        """Return the center of the detected region."""
        return self.x + self.width // 2, self.y + self.height // 2

    @property
    def box(self) -> tuple[int, int, int, int]:
        """Return the bounding box as x, y, width, height."""
        return self.x, self.y, self.width, self.height


class ColorDetector:
    """Detects objects by color in a BGR or BGRA frame."""

    def detect(
        self,
        frame: np.ndarray,
        target: tuple[int, int, int],
        tolerance: int = 30,
    ) -> DetectionResult | None:
        """
        Return the largest region matching a BGR color.

        Args:
            frame: BGR or BGRA image.
            target: BGR color tuple.
            tolerance: Per-channel color distance.

        Returns:
            Largest DetectionResult or None when no pixels match.
        """
        matches = self.find_many(frame, target, tolerance)

        if not matches:
            return None

        return max(matches, key=lambda match: match.area)

    def find_many(
        self,
        frame: np.ndarray,
        target: tuple[int, int, int],
        tolerance: int = 30,
    ) -> list[DetectionResult]:
        """Return all connected regions matching a BGR color."""
        source = _to_bgr(frame)

        blue, green, red = target
        lower = np.array(
            [max(0, blue - tolerance), max(0, green - tolerance), max(0, red - tolerance)],
            dtype=np.uint8,
        )
        upper = np.array(
            [min(255, blue + tolerance), min(255, green + tolerance), min(255, red + tolerance)],
            dtype=np.uint8,
        )

        mask = cv2.inRange(source, lower, upper)
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        results: list[DetectionResult] = []

        for contour in contours:
            x, y, width, height = cv2.boundingRect(contour)

            results.append(
                DetectionResult(
                    x=int(x),
                    y=int(y),
                    width=int(width),
                    height=int(height),
                    area=int(cv2.contourArea(contour)),
                )
            )

        return results


def _to_bgr(frame: np.ndarray) -> np.ndarray:
    if frame.ndim == 2:
        return cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)

    if frame.shape[2] == 4:
        return cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)

    return frame
