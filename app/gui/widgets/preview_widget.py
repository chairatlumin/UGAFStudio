from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QLabel


class PreviewWidget(QLabel):
    """Displays the latest captured frame."""

    def __init__(self) -> None:
        super().__init__()

        self.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.setText("Waiting for Capture...")

        self.setMinimumSize(960, 540)

    def set_frame(self, pixmap: QPixmap) -> None:
        """Display captured frame."""

        self.setPixmap(
            pixmap.scaled(
                self.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )
