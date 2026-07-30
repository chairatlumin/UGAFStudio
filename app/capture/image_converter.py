from __future__ import annotations

import cv2
import numpy as np
from PySide6.QtGui import QImage, QPixmap


class ImageConverter:
    """Convert image formats."""

    @staticmethod
    def to_qimage(frame: np.ndarray) -> QImage:
        """Convert BGRA NumPy image to QImage."""

        rgb = cv2.cvtColor(frame, cv2.COLOR_BGRA2RGB)

        height, width, channels = rgb.shape

        bytes_per_line = channels * width

        return QImage(
            rgb.data,
            width,
            height,
            bytes_per_line,
            QImage.Format.Format_RGB888,
        ).copy()

    @staticmethod
    def to_pixmap(frame: np.ndarray) -> QPixmap:
        """Convert BGRA NumPy image to QPixmap."""

        return QPixmap.fromImage(ImageConverter.to_qimage(frame))
