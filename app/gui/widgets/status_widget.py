from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel


class StatusWidget(QLabel):
    """Displays runtime status."""

    def __init__(self) -> None:
        super().__init__()

        self.setAlignment(Qt.AlignmentFlag.AlignLeft)

        self._fps: float = 0.0
        self._mouse_x: int = 0
        self._mouse_y: int = 0
        self._resolution: str = "-"
        self._pixel: str = "-"

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

    def set_pixel(self, pixel: str) -> None:
        self._pixel = pixel
        self._refresh()

    def _refresh(self) -> None:
        self.setText(
            (
                f"FPS : {self._fps:.1f}\n"
                f"Mouse : {self._mouse_x}, {self._mouse_y}\n"
                f"Resolution : {self._resolution}\n"
                f"Pixel : {self._pixel}"
            )
        )
