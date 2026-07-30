from __future__ import annotations

from PySide6.QtCore import QObject, QTimer

from app.capture.capture_service import CaptureService
from app.capture.image_converter import ImageConverter
from app.core.fps import FPSCounter
from app.gui.widgets.preview_widget import PreviewWidget
from app.gui.widgets.status_widget import StatusWidget


class CaptureController(QObject):
    """Control desktop capture and update UI."""

    def __init__(
        self,
        preview: PreviewWidget,
        status: StatusWidget,
    ) -> None:
        super().__init__()

        self._preview = preview
        self._status = status

        self._capture = CaptureService()
        self._fps = FPSCounter()

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._update)

    def start(self) -> None:
        """Start capture."""

        self._timer.start(33)

    def stop(self) -> None:
        """Stop capture."""

        self._timer.stop()

    def _update(self) -> None:
        """Capture one frame."""

        frame = self._capture.capture()

        pixmap = ImageConverter.to_pixmap(frame)

        self._preview.set_frame(pixmap)

        fps = self._fps.tick()

        self._status.set_fps(fps)

        width, height = self._capture.monitor_size()

        self._status.set_resolution(f"{width} x {height}")
