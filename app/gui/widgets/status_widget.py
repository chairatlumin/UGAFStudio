from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel

from app.vision.pixel_inspector import PixelColor


class StatusWidget(QLabel):
    """Displays runtime information."""

    def __init__(self) -> None:
        super().__init__()

        self.setAlignment(Qt.AlignmentFlag.AlignLeft)

        self._fps = 0.0
        self._mouse_x = 0
        self._mouse_y = 0
        self._resolution = "-"
        self._pixel: PixelColor | None = None

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

    def set_pixel(self, pixel: PixelColor | None) -> None:
        self._pixel = pixel
        self._refresh()

    def _refresh(self) -> None:
        pixel_text = "-"

        if self._pixel is not None:
            red, green, blue = self._pixel.rgb
            pixel_text = f"RGB({red}, {green}, {blue})  HEX {self._pixel.hex}"

        self.setText(
            f"""FPS : {self._fps:.1f}
Mouse : {self._mouse_x}, {self._mouse_y}
Resolution : {self._resolution}
Pixel : {pixel_text}
"""
        )
