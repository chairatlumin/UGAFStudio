"""Macro Controller: orchestrates recording/playback between GUI and services."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import QObject

from app.automation.capture import LiveCapture
from app.automation.macro import MacroPlayer, MacroRecorder, steps_from_json, steps_to_json
from app.automation.macro_recorder import CapturingRecorder
from app.input.keyboard_service import KeyboardService
from app.input.mouse_service import MouseService

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from app.gui.widgets.macro_recorder_widget import MacroRecorderWidget


class MacroController(QObject):
    """Orchestrates macro recording/playback between GUI and services."""

    def __init__(
        self,
        mouse_service: MouseService,
        keyboard_service: KeyboardService,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._mouse = mouse_service
        self._keyboard = keyboard_service
        self._widget: MacroRecorderWidget | None = None
        self._recorder = MacroRecorder()
        self._capture = LiveCapture()
        self._bridge = CapturingRecorder(self._recorder)
        self._capture.set_listener(self._bridge)

    def set_widget(self, widget: MacroRecorderWidget) -> None:
        self._widget = widget
        widget.set_controller(self)

    def record(self) -> None:
        """Start live capture recording."""
        self._recorder.start()
        self._capture.start()

    def stop(self) -> None:
        """Stop recording and update widget with captured steps."""
        self._capture.stop()
        steps = self._recorder.stop()
        if self._widget is not None:
            for step in steps:
                self._widget.add_step(step)

    def play(self, speed: float = 1.0) -> None:
        """Replay the recorded steps."""
        was_recording = self._recorder.recording
        steps = self._recorder.stop() if was_recording else self._recorder.steps
        player = MacroPlayer(mouse=self._mouse, keyboard=self._keyboard)
        player.play(steps, speed=speed)
        if was_recording:
            self._recorder.start()

    def load(self, path: Path) -> None:
        """Load a macro from a JSON file."""
        data = path.read_text(encoding="utf-8")
        steps = steps_from_json(data)
        if self._widget is not None:
            self._widget.set_steps(steps)

    def save(self, path: Path) -> None:
        """Save current macro steps to a JSON file."""
        steps = self._recorder.steps
        path.write_text(steps_to_json(steps), encoding="utf-8")

    def clear(self) -> None:
        """Clear all recorded steps."""
        self._recorder = MacroRecorder()
        self._bridge = CapturingRecorder(self._recorder)
        self._capture.set_listener(self._bridge)
