from __future__ import annotations

from typing import Any, Callable


class HotkeyService:
    """Registers global hotkeys using the keyboard library."""

    def __init__(self) -> None:
        self._keyboard: Any = None
        self._handles: list[Any] = []

    def available(self) -> bool:
        """Return whether the global hotkey backend can be loaded."""
        if self._keyboard is None:
            try:
                import keyboard

                self._keyboard = keyboard
            except ImportError, OSError:
                return False

        return True

    def register(self, hotkey: str, callback: Callable[[], None]) -> bool:
        """
        Register a global hotkey.

        Args:
            hotkey: Combination such as "ctrl+shift+p".
            callback: Function invoked when the hotkey is pressed.

        Returns:
            True when the hotkey was registered.
        """
        if not self.available():
            return False

        handle = self._keyboard.add_hotkey(hotkey, callback)
        self._handles.append(handle)

        return True

    def unregister_all(self) -> None:
        """Remove all registered hotkeys."""
        if not self.available():
            return

        for handle in self._handles:
            try:
                self._keyboard.remove_hotkey(handle)
            except KeyError:
                pass

        self._handles.clear()
