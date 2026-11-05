from __future__ import annotations

import os
from typing import cast

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from app.gui.main_window import MainWindow  # noqa: E402
from app.gui.widgets.health_widget import HealthWidget  # noqa: E402
from app.services.runtime_health import RuntimeCheck  # noqa: E402


@pytest.fixture(scope="module")
def app() -> QApplication:
    return cast(QApplication, QApplication.instance() or QApplication([]))


def test_main_window_builds(app: QApplication) -> None:
    window = MainWindow()

    try:
        assert window.preview_widget is not None
        assert window.status_widget is not None
        assert window.dashboard_widget is not None
        assert window.qa_command_center_widget is not None
        assert window.health_widget is not None
        assert window.logger_widget is not None
    finally:
        window.capture_controller.stop()
        window.close()


def test_main_window_has_menus(app: QApplication) -> None:
    window = MainWindow()

    try:
        actions = [action.text() for action in window.menuBar().actions()]
        tabs = [window.tabs.tabText(index) for index in range(window.tabs.count())]
        assert "Capture" in actions
        assert "QA" in actions
        assert "System Health" in tabs
        assert "TA Optimize" in tabs
    finally:
        window.capture_controller.stop()
        window.close()


def test_main_window_theme_keeps_tabs_and_dashboard_readable(app: QApplication) -> None:
    window = MainWindow()

    try:
        stylesheet = window.styleSheet()
        assert "QTabBar::tab:selected" in stylesheet
        assert "color: #11695f" in stylesheet
        assert "background: #ffffff" in stylesheet
        assert "color:#243442" in window.dashboard_widget._total.styleSheet()
        assert "color:#18704a" in window.dashboard_widget._passed.styleSheet()
        assert window.dashboard_widget._table.alternatingRowColors()
    finally:
        window.capture_controller.stop()
        window.close()


def test_show_workbench_selects_the_demo_profile(app: QApplication) -> None:
    window = MainWindow()
    try:
        window.show_workbench()
        assert window.tabs.currentWidget() is window.qa_workbench_widget
        assert window.qa_workbench_widget._profiles.currentText() == "highschoolblood-demo"
    finally:
        window.capture_controller.stop()
        window.close()


def test_health_widget_shows_bounded_diagnostic_results(app: QApplication, monkeypatch) -> None:
    monkeypatch.setattr(
        "app.gui.widgets.health_widget.collect_runtime_health",
        lambda: [
            RuntimeCheck("Runtime", "READY", "frozen EXE"),
            RuntimeCheck("VLM", "UNAVAILABLE", "model server offline"),
        ],
    )
    widget = HealthWidget()
    try:
        widget.run_check()
        assert widget._table.rowCount() == 2
        assert widget._table.item(1, 1).text() == "UNAVAILABLE"
        assert "พร้อม 1/2" in widget._summary.text()
        assert widget._refresh.isEnabled()
    finally:
        widget.close()
