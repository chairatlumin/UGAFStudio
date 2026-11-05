"""Capture-to-Macro bridge: forwards LiveCapture events to MacroRecorder."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from app.automation.macro import MacroRecorder

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    pass


class CapturingRecorder:
    """Bridges LiveCapture events to MacroRecorder steps.

    Wraps a MacroRecorder and records actions as they arrive from live input.
    Mouse moves are filtered by a distance threshold to avoid noise.
    """

    def __init__(
        self,
        recorder: MacroRecorder,
        *,
        capture_mouse_move: bool = False,
        mouse_move_threshold: int = 50,
    ) -> None:
        self._recorder = recorder
        self._capture_mouse_move = capture_mouse_move
        self._mouse_move_threshold = mouse_move_threshold
        self._last_mouse_pos: tuple[int, int] | None = None

    def on_key_press(self, key: str) -> None:
        self._recorder.record_key(key)

    def on_key_release(self, key: str) -> None:
        pass

    def on_mouse_move(self, x: int, y: int) -> None:
        if not self._capture_mouse_move:
            return
        if self._last_mouse_pos is not None:
            dx = x - self._last_mouse_pos[0]
            dy = y - self._last_mouse_pos[1]
            if abs(dx) < self._mouse_move_threshold and abs(dy) < self._mouse_move_threshold:
                return
        self._last_mouse_pos = (x, y)
        self._recorder.record_move(x, y)

    def on_mouse_click(self, x: int, y: int, button: str, pressed: bool) -> None:
        if pressed:
            self._recorder.record_click(x, y, button)

    def on_mouse_scroll(self, x: int, y: int, dx: int, dy: int) -> None:
        self._recorder.record_scroll(dy)
