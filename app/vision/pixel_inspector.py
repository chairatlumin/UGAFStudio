from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class PixelColor:
    """RGB and HEX color sampled from a frame."""

    red: int
    green: int
    blue: int

    @property
    def hex(self) -> str:
        """Return color as uppercase HEX."""

        return f"#{self.red:02X}{self.green:02X}{self.blue:02X}"

    @property
    def rgb(self) -> tuple[int, int, int]:
        """Return color as an RGB tuple."""

        return self.red, self.green, self.blue


class PixelInspector:
    """Reads pixel colors from captured BGRA frames."""

    def inspect(
        self,
        frame: np.ndarray,
        x: int,
        y: int,
    ) -> PixelColor | None:
        """Return RGB color at frame-local coordinates."""

        height, width = frame.shape[:2]

        if x < 0 or y < 0 or x >= width or y >= height:
            return None

        blue, green, red = frame[y, x, :3]

        return PixelColor(
            red=int(red),
            green=int(green),
            blue=int(blue),
        )
