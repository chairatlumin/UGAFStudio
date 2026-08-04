from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QMainWindow,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from app.capture.monitor import MonitorInfo
from app.controllers.capture_controller import CaptureController
from app.controllers.qa_controller import QAController
from app.gui.style import STYLE
from app.gui.widgets.dashboard_widget import DashboardWidget
from app.gui.widgets.logger_widget import LoggerWidget
from app.gui.widgets.preview_widget import PreviewWidget
from app.gui.widgets.region_selector import RegionSelector
from app.gui.widgets.status_widget import StatusWidget
from app.qa.test_case import TestRunner


class MainWindow(QMainWindow):
    """Main application window."""

    def __init__(self) -> None:
        super().__init__()

        self.setWindowTitle("UGAF Studio v0.1.0")
        self.resize(1400, 900)
        self.setStyleSheet(STYLE)

        self.preview_widget = PreviewWidget()
        self.status_widget = StatusWidget()
        self.dashboard_widget = DashboardWidget()
        self.logger_widget = LoggerWidget()

        self._selector: RegionSelector | None = None

        self.capture_controller = CaptureController(
            preview=self.preview_widget,
            status=self.status_widget,
        )
        self.qa_controller = QAController()

        self._build_ui()
        self._build_menu()

        self.capture_controller.start()

    def _build_ui(self) -> None:
        """Build application UI."""

        central = QWidget()

        self.setCentralWidget(central)

        layout = QVBoxLayout()

        central.setLayout(layout)

        tabs = QTabWidget()

        preview_page = QWidget()
        preview_layout = QVBoxLayout()
        preview_layout.setContentsMargins(0, 0, 0, 0)
        preview_layout.addWidget(self.preview_widget)
        preview_layout.addWidget(self.status_widget)
        preview_page.setLayout(preview_layout)

        tabs.addTab(preview_page, "Preview")
        tabs.addTab(self.dashboard_widget, "Dashboard")

        layout.addWidget(tabs)
        layout.addWidget(self.logger_widget)

    def _build_menu(self) -> None:
        """Build application menus."""

        capture_menu = self.menuBar().addMenu("Capture")

        screenshot_action = capture_menu.addAction("Screenshot")
        screenshot_action.triggered.connect(self._on_screenshot)

        region_action = capture_menu.addAction("Region Capture")
        region_action.triggered.connect(self._on_region)

        qa_menu = self.menuBar().addMenu("QA")

        run_action = qa_menu.addAction("Run Demo Tests")
        run_action.triggered.connect(self._on_run_demo)

    def _on_screenshot(self) -> None:
        path = self.capture_controller.capture_screenshot()
        self.logger_widget.info(f"Screenshot saved: {path}")

    def _on_region(self) -> None:
        self._selector = RegionSelector()
        self._selector.selected.connect(self._on_region_selected)
        self._selector.show()

    def _on_region_selected(self, monitor: MonitorInfo) -> None:
        if self._selector is not None:
            self._selector.deleteLater()
            self._selector = None

        path = self.capture_controller.capture_region(monitor)
        self.logger_widget.info(f"Region saved: {path}")

    def _on_run_demo(self) -> None:
        results = self.qa_controller.run_demo()
        self.dashboard_widget.set_results(results)

        summary = TestRunner.summary(results)
        self.logger_widget.info(f"Demo suite complete: {summary}")

        report = self.qa_controller.generate_report(results, Path("reports"))
        self.logger_widget.info(f"Report saved: {report}")
