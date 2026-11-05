"""Tests for MacroRecorderWidget."""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QApplication

from app.automation.macro import MacroStep
from app.gui.widgets.macro_recorder_widget import MacroRecorderWidget


@pytest.fixture(scope="session")
def qapp() -> QApplication:
    """Create a QApplication instance for the test session."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


class TestMacroRecorderWidget:
    def test_widget_creates_with_all_child_widgets(self, qapp: QApplication) -> None:
        widget = MacroRecorderWidget()
        assert widget._record_btn is not None
        assert widget._play_btn is not None
        assert widget._save_btn is not None
        assert widget._load_btn is not None
        assert widget._clear_btn is not None
        assert widget._steps_list is not None
        assert widget._status_label is not None
        assert widget._speed_spin is not None

    def test_record_button_toggles(self, qapp: QApplication) -> None:
        widget = MacroRecorderWidget()
        assert widget._record_btn.isChecked() is False
        widget._record_btn.click()
        assert widget._record_btn.isChecked() is True
        widget._record_btn.click()
        assert widget._record_btn.isChecked() is False

    def test_add_step_updates_list(self, qapp: QApplication) -> None:
        widget = MacroRecorderWidget()
        step = MacroStep(action="key", params={"key": "a"}, delay_ms=100.0)
        widget.add_step(step)
        assert widget._steps_list.count() == 1
        assert "key" in widget._steps_list.item(0).text()

    def test_set_steps_replaces_all(self, qapp: QApplication) -> None:
        widget = MacroRecorderWidget()
        steps = [
            MacroStep(action="move", params={"x": 10, "y": 20}, delay_ms=0.0),
            MacroStep(action="click", params={"x": 30, "y": 40, "button": "left"}, delay_ms=500.0),
        ]
        widget.set_steps(steps)
        assert widget._steps_list.count() == 2
        assert "move" in widget._steps_list.item(0).text()
        assert "click" in widget._steps_list.item(1).text()

    def test_clear_resets_steps(self, qapp: QApplication) -> None:
        widget = MacroRecorderWidget()
        step = MacroStep(action="key", params={"key": "a"}, delay_ms=0.0)
        widget.add_step(step)
        widget._on_clear()
        assert widget._steps_list.count() == 0
        assert len(widget._steps) == 0

    def test_speed_spin_range(self, qapp: QApplication) -> None:
        widget = MacroRecorderWidget()
        assert widget._speed_spin.minimum() == 1
        assert widget._speed_spin.maximum() == 100
        assert widget._speed_spin.value() == 10

    def test_format_params_empty(self, qapp: QApplication) -> None:
        widget = MacroRecorderWidget()
        assert widget._format_params({}) == ""

    def test_format_params_multiple(self, qapp: QApplication) -> None:
        widget = MacroRecorderWidget()
        result = widget._format_params({"x": 10, "y": 20})
        assert "x=10" in result
        assert "y=20" in result

    def test_start_recording_updates_ui(self, qapp: QApplication) -> None:
        widget = MacroRecorderWidget()
        widget._start_recording()
        assert widget._recording is True
        assert "Recording" in widget._status_label.text()
        widget._stop_recording()

    def test_stop_recording_updates_ui(self, qapp: QApplication) -> None:
        widget = MacroRecorderWidget()
        widget._start_recording()
        widget._stop_recording()
        assert widget._recording is False
        assert "Stopped" in widget._status_label.text()
