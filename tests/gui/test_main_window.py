from __future__ import annotations

import os
from typing import cast

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from app.gui.main_window import MainWindow  # noqa: E402


@pytest.fixture(scope="module")
def app() -> QApplication:
    return cast(QApplication, QApplication.instance() or QApplication([]))


def test_main_window_builds(app: QApplication) -> None:
    window = MainWindow()

    try:
        assert window.preview_widget is not None
        assert window.status_widget is not None
        assert window.dashboard_widget is not None
        assert window.logger_widget is not None
    finally:
        window.capture_controller.stop()
        window.close()


def test_main_window_has_menus(app: QApplication) -> None:
    window = MainWindow()

    try:
        actions = [action.text() for action in window.menuBar().actions()]
        assert "Capture" in actions
        assert "QA" in actions
    finally:
        window.capture_controller.stop()
        window.close()
