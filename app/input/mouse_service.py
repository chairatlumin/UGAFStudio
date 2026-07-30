from __future__ import annotations

from PySide6.QtCore import QPoint
from PySide6.QtGui import QCursor


class MouseService:
    """Provides mouse information."""

    def position(self) -> tuple[int, int]:
        """Return current mouse position."""

        pos: QPoint = QCursor.pos()

        return pos.x(), pos.y()
