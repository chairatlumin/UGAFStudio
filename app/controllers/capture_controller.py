from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QTimer

from app.capture.capture_service import CaptureService
from app.capture.image_converter import ImageConverter
from app.capture.monitor import MonitorInfo
from app.capture.screenshot_service import ScreenshotService
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
        self._screenshots = ScreenshotService()

        self._timer = QTimer()
        self._timer.timeout.connect(self._update)

    def start(self) -> None:
        """Start capture loop."""
        self._timer.start(33)

    def stop(self) -> None:
        """Stop capture loop."""
        self._timer.stop()

    def capture_screenshot(self, name: str | None = None) -> Path:
        """Save the current monitor as a PNG screenshot."""
        frame = self._capture.capture()

        return self._screenshots.save(frame, name=name)

    def capture_region(self, monitor: MonitorInfo, name: str | None = None) -> Path:
        """Capture a screen region and save it as a PNG screenshot."""
        frame = self._capture.capture_region(monitor)

        return self._screenshots.save(frame, name=name)

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

        monitor = self._capture.current_monitor()
        local_x, local_y = monitor.to_local(mouse_x, mouse_y)

        pixel = self._pixel_inspector.inspect(
            frame=frame,
            x=local_x,
            y=local_y,
        )

        self._status.set_pixel(pixel)

        width, height = monitor.size

        self._status.set_resolution(f"{width} x {height}")
