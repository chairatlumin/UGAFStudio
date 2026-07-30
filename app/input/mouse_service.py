from __future__ import annotations

from PySide6.QtGui import QCursor


class MouseService:
    """Provides current mouse position."""

    def position(self) -> tuple[int, int]:
        pos = QCursor.pos()

        return pos.x(), pos.y()
