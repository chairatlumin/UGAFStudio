"""Live keyboard + mouse capture via pynput.

Captures real user input during macro recording. Runs in daemon threads
(non-blocking) and forwards events to a listener.
"""

from __future__ import annotations

import logging
from typing import Protocol

logger = logging.getLogger(__name__)


class CaptureListener(Protocol):
    """Receives raw input events during live capture."""

    def on_key_press(self, key: str) -> None: ...
    def on_key_release(self, key: str) -> None: ...
    def on_mouse_move(self, x: int, y: int) -> None: ...
    def on_mouse_click(self, x: int, y: int, button: str, pressed: bool) -> None: ...
    def on_mouse_scroll(self, x: int, y: int, dx: int, dy: int) -> None: ...


class _Listener(Protocol):
    """Minimal protocol for pynput listeners."""

    def start(self) -> None: ...
    def stop(self) -> None: ...


class LiveCapture:
    """Captures keyboard + mouse events via pynput and forwards to a listener."""

    def __init__(self, listener: CaptureListener | None = None) -> None:
        self._listener = listener
        self._keyboard_listener: _Listener | None = None
        self._mouse_listener: _Listener | None = None
        self._capturing = False

    @property
    def capturing(self) -> bool:
        return self._capturing

    def set_listener(self, listener: CaptureListener | None) -> None:
        self._listener = listener

    def start(self) -> None:
        """Start listening to keyboard + mouse. Non-blocking (uses pynput threads)."""
        if self._capturing:
            return
        import pynput

        self._keyboard_listener = pynput.keyboard.Listener(
            on_press=self._on_key_press,
            on_release=self._on_key_release,
        )
        self._mouse_listener = pynput.mouse.Listener(
            on_move=self._on_mouse_move,
            on_click=self._on_mouse_click,
            on_scroll=self._on_mouse_scroll,
        )
        self._keyboard_listener.start()
        self._mouse_listener.start()
        self._capturing = True

    def stop(self) -> None:
        """Stop all listeners."""
        if not self._capturing:
            return
        try:
            if self._keyboard_listener is not None:
                self._keyboard_listener.stop()
            if self._mouse_listener is not None:
                self._mouse_listener.stop()
        except Exception as exc:  # noqa: BLE001
            logger.debug("Error stopping capture: %s", exc)
        self._keyboard_listener = None
        self._mouse_listener = None
        self._capturing = False

    def _on_key_press(self, key: object) -> None:
        k = _key_to_string(key)
        if k and self._listener is not None:
            self._listener.on_key_press(k)

    def _on_key_release(self, key: object) -> None:
        k = _key_to_string(key)
        if k and self._listener is not None:
            self._listener.on_key_release(k)

    def _on_mouse_move(self, x: int, y: int) -> None:
        if self._listener is not None:
            self._listener.on_mouse_move(x, y)

    def _on_mouse_click(self, x: int, y: int, button: object, pressed: bool) -> None:
        b = _button_to_string(button)
        if self._listener is not None:
            self._listener.on_mouse_click(x, y, b, pressed)

    def _on_mouse_scroll(self, x: int, y: int, dx: int, dy: int) -> None:
        if self._listener is not None:
            self._listener.on_mouse_scroll(x, y, dx, dy)


def _key_to_string(key: object) -> str:
    """Convert a pynput key object to a string name."""
    char = getattr(key, "char", None)
    if char is not None:
        return str(char)
    name = getattr(key, "name", None)
    if name is not None:
        return str(name)
    return ""


def _button_to_string(button: object) -> str:
    """Convert a pynput button object to a string name."""
    name = getattr(button, "name", None)
    if name is not None:
        return str(name)
    return "unknown"
