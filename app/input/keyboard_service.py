from __future__ import annotations

from typing import Any


class KeyboardService:
    """Simulates keyboard input through a controller.

    The controller defaults to pyautogui and can be injected for testing.
    """

    def __init__(self, controller: Any | None = None) -> None:
        self._controller = controller if controller is not None else _load_controller()

    def press(self, key: str) -> None:
        """Press and release a single key."""
        self._controller.press(key)

    def hold(self, key: str) -> None:
        """Press and hold a key."""
        self._controller.keyDown(key)

    def release(self, key: str) -> None:
        """Release a held key."""
        self._controller.keyUp(key)

    def hotkey(self, *keys: str) -> None:
        """Press a combination of keys in order."""
        self._controller.hotkey(*keys)

    def write(self, text: str, interval: float = 0.0) -> None:
        """Type text as keyboard input."""
        self._controller.write(text, interval=interval)


def _load_controller() -> Any:
    import pyautogui

    return pyautogui
