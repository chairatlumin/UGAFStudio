from __future__ import annotations

from pathlib import Path
from typing import Any

import cv2
import numpy as np

from app.utils.file import ensure_directory, unique_path


class ScreenshotService:
    """Saves captured frames to disk."""

    def __init__(self, output_dir: Path = Path("screenshots")) -> None:
        self.output_dir = ensure_directory(output_dir)

    def save(self, frame: np.ndarray, name: str | None = None) -> Path:
        """
        Write a BGRA frame as a PNG image.

        Args:
            frame: BGRA numpy image.
            name: Optional output name without extension.

        Returns:
            Path of the saved image.
        """
        prefix = name if name else "screenshot"
        path = unique_path(self.output_dir, prefix, "png")

        ok: Any = cv2.imwrite(str(path), frame)

        if not ok:
            raise OSError(f"Failed to write image: {path}")

        return path
