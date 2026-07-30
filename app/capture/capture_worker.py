from __future__ import annotations

from PySide6.QtCore import QObject, QTimer, Signal

from app.capture.capture_service import CaptureService
from app.capture.image_converter import ImageConverter


class CaptureWorker(QObject):
    frame_ready = Signal(object)

    def __init__(self) -> None:
        super().__init__()

        self.capture = CaptureService()

        self.timer = QTimer()

        self.timer.timeout.connect(self.update)

    def start(self) -> None:
        self.timer.start(33)

    def stop(self) -> None:
        self.timer.stop()

    def update(self) -> None:
        frame = self.capture.capture()

        pixmap = ImageConverter.to_pixmap(frame)

        self.frame_ready.emit(pixmap)
