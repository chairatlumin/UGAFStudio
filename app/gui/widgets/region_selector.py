from __future__ import annotations

from PySide6.QtCore import QPoint, QRect, Qt, Signal
from PySide6.QtGui import QColor, QGuiApplication, QMouseEvent, QPainter, QPainterPath, QPaintEvent
from PySide6.QtWidgets import QWidget

from app.capture.monitor import MonitorInfo


class RegionSelector(QWidget):
    """Full-screen overlay used to drag-select a screen region."""

    selected = Signal(object)

    def __init__(self) -> None:
        super().__init__()

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setCursor(Qt.CursorShape.CrossCursor)

        self._start: QPoint | None = None
        self._current: QPoint | None = None

        self.setGeometry(self._desktop_geometry())

    def _desktop_geometry(self) -> QRect:
        union = QRect()

        for screen in QGuiApplication.screens():
            union = union.united(screen.geometry())

        return union

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._start = event.globalPosition().toPoint()
            self._current = self._start
            self.update()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        self._current = event.globalPosition().toPoint()
        self.update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() != Qt.MouseButton.LeftButton or self._start is None:
            return

        end = event.globalPosition().toPoint()
        self._current = end

        monitor = self._region_from_points(self._start, end)

        self.close()
        self.selected.emit(monitor)

    def keyPressEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        if event.key() == Qt.Key.Key_Escape:
            self.close()

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)

        painter.fillRect(self.rect(), QColor(0, 0, 0, 120))

        if self._start is not None and self._current is not None:
            region = self._region_from_points(self._start, self._current)
            rect = self._selection_rect(region)

            path = QPainterPath()
            path.addRect(self.rect())
            path.addRect(rect)
            painter.fillPath(path, QColor(0, 0, 0, 160))

            painter.setPen(QColor(255, 255, 255, 255))
            painter.drawRect(rect)

            painter.drawText(
                rect.adjusted(4, 4, -4, -4),
                f"{region.width} x {region.height}",
            )

        painter.end()

    def _region_from_points(self, start: QPoint, end: QPoint) -> MonitorInfo:
        left = min(start.x(), end.x())
        top = min(start.y(), end.y())
        width = abs(start.x() - end.x()) + 1
        height = abs(start.y() - end.y()) + 1

        return MonitorInfo(left=left, top=top, width=width, height=height)

    def _selection_rect(self, region: MonitorInfo) -> QRect:
        """Return the selection rectangle in widget-local coordinates."""

        origin = self.pos()

        return QRect(
            region.left - origin.x(),
            region.top - origin.y(),
            region.width,
            region.height,
        )
