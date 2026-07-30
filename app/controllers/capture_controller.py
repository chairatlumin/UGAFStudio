from __future__ import annotations

from PySide6.QtCore import QTimer

from app.capture.capture_service import CaptureService
from app.capture.image_converter import ImageConverter
from app.core.fps import FPSCounter
from app.gui.widgets.preview_widget import PreviewWidget
from app.gui.widgets.status_widget import StatusWidget
from app.input.mouse_service import MouseService
from app.vision.pixel_inspector import PixelInspector


class CaptureController:
    """Controls desktop capture and updates the UI."""

    def __init__(
        self,
        preview: PreviewWidget,
        status: StatusWidget,
    ) -> None:
        self._preview = preview
        self._status = status

        self._capture = CaptureService()
        self._mouse = MouseService()
        self._fps = FPSCounter()
        self._pixel_inspector = PixelInspector()

        self._timer = QTimer()
        self._timer.timeout.connect(self._update)

    def start(self) -> None:
        """Start capture loop."""
        self._timer.start(33)

    def stop(self) -> None:
        """Stop capture loop."""
        self._timer.stop()

    def _update(self) -> None:
        """Update preview and status."""

        frame = self._capture.capture()

        pixmap = ImageConverter.to_pixmap(frame)

        self._preview.set_frame(pixmap)

        fps = self._fps.tick()

        self._status.set_fps(fps)

        mouse_x, mouse_y = self._mouse.position()

        self._status.set_mouse(
            mouse_x,
            mouse_y,
        )

        monitor_x, monitor_y = self._capture.monitor_origin()
        pixel = self._pixel_inspector.inspect(
            frame=frame,
            x=mouse_x - monitor_x,
            y=mouse_y - monitor_y,
        )

        self._status.set_pixel(pixel)

        width, height = self._capture.monitor_size()

        self._status.set_resolution(f"{width} x {height}")
