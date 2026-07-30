from __future__ import annotations

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QMainWindow,
    QVBoxLayout,
    QWidget,
)

from app.capture.capture_service import CaptureService
from app.capture.image_converter import ImageConverter
from app.core.fps import FPSCounter
from app.gui.style import STYLE
from app.gui.widgets.preview_widget import PreviewWidget
from app.gui.widgets.status_widget import StatusWidget


class MainWindow(QMainWindow):
    """Main application window."""

    def __init__(self) -> None:
        super().__init__()

        self.setWindowTitle("UGAF Studio v0.0.1")
        self.resize(1400, 900)
        self.setStyleSheet(STYLE)

        # Services
        self.capture_service = CaptureService()
        self.fps_counter = FPSCounter()

        # UI
        self.preview_widget = PreviewWidget()
        self.status_widget = StatusWidget()

        self._build_ui()

        # Timer (~30 FPS)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._update_frame)
        self.timer.start(33)

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)

        layout = QVBoxLayout()
        central.setLayout(layout)

        layout.addWidget(self.preview_widget)
        layout.addWidget(self.status_widget)

    def _update_frame(self) -> None:
        frame = self.capture_service.capture()

        pixmap = ImageConverter.to_pixmap(frame)

        self.preview_widget.set_frame(pixmap)

        fps = self.fps_counter.tick()

        self.status_widget.set_fps(fps)

        width, height = self.capture_service.monitor_size()

        self.status_widget.set_resolution(f"{width} x {height}")
