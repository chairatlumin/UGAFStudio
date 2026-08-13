from __future__ import annotations

from typing import Any

from PySide6.QtCore import QPoint
from PySide6.QtGui import QCursor


class MouseService:
    """Provides mouse information and control.

    Position is read through Qt; movement and clicks are delegated to a
    controller that defaults to pyautogui. A controller can be injected for
    testing.
    """

    def __init__(self, controller: Any | None = None) -> None:
        self._controller = controller if controller is not None else _load_controller()

    def position(self) -> tuple[int, int]:
        """Return current mouse position in screen coordinates."""
        pos: QPoint = QCursor.pos()

        return pos.x(), pos.y()

    def move(self, x: int, y: int, duration: float = 0.0) -> None:
        """Move the cursor to a screen coordinate."""
        self._controller.moveTo(x, y, duration=duration)

    def click(
        self,
        x: int | None = None,
        y: int | None = None,
        button: str = "left",
        clicks: int = 1,
    ) -> None:
        """Click a button at a screen coordinate."""
        self._controller.click(x, y, button=button, clicks=clicks)

    def double_click(self, x: int | None = None, y: int | None = None) -> None:
        """Double-click a button at a screen coordinate."""
        self.click(x, y, clicks=2)

    def drag(
        self,
        start: tuple[int, int],
        end: tuple[int, int],
        duration: float = 0.2,
        button: str = "left",
    ) -> None:
        """Drag the cursor from start to end while holding a button."""
        self._controller.moveTo(start[0], start[1], duration=duration / 2)
        self._controller.dragTo(end[0], end[1], duration=duration, button=button)

    def scroll(self, amount: int) -> None:
        """Scroll the wheel by a number of clicks."""
        self._controller.scroll(amount)


def _load_controller() -> Any:
    import pyautogui

    return pyautogui
