from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel


class StatusWidget(QLabel):
    """Displays runtime information."""

    def __init__(self) -> None:
        super().__init__()

        self.setAlignment(Qt.AlignmentFlag.AlignLeft)

        self._fps = 0.0
        self._mouse_x = 0
        self._mouse_y = 0
        self._resolution = "-"

        self._refresh()

    def set_fps(self, fps: float) -> None:
        self._fps = fps
        self._refresh()

    def set_mouse(self, x: int, y: int) -> None:
        self._mouse_x = x
        self._mouse_y = y
        self._refresh()

    def set_resolution(self, resolution: str) -> None:
        self._resolution = resolution
        self._refresh()

    def _refresh(self) -> None:
        self.setText(
            f"""FPS : {self._fps:.1f}
Mouse : {self._mouse_x}, {self._mouse_y}
Resolution : {self._resolution}
Pixel : -
"""
        )
