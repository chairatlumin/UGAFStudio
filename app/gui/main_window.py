from __future__ import annotations

from PySide6.QtWidgets import (
    QMainWindow,
    QVBoxLayout,
    QWidget,
)

from app.controllers.capture_controller import CaptureController
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

        self.preview_widget = PreviewWidget()
        self.status_widget = StatusWidget()

        self._build_ui()

        self.capture_controller = CaptureController(
            preview=self.preview_widget,
            status=self.status_widget,
        )

        self.capture_controller.start()

    def _build_ui(self) -> None:
        """Build application UI."""

        central = QWidget()

        self.setCentralWidget(central)

        layout = QVBoxLayout()

        central.setLayout(layout)

        layout.addWidget(self.preview_widget)

        layout.addWidget(self.status_widget)
