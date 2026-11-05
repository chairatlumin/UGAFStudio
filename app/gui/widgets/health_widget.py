from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.services.runtime_health import RuntimeCheck, collect_runtime_health


class HealthWidget(QWidget):
    """Non-blocking local diagnostics for packaged app dependencies."""

    def __init__(self) -> None:
        super().__init__()
        self._refresh = QPushButton("ตรวจสุขภาพระบบ")
        self._refresh.setObjectName("refreshRuntimeHealth")
        self._summary = QLabel("ยังไม่ได้ตรวจ dependency · ตรวจนี้ไม่ส่งภาพหรือ input เข้าเกม")
        self._table = QTableWidget(0, 3)
        self._table.setHorizontalHeaderLabels(["Component", "Status", "Details"])
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setWordWrap(True)
        self._refresh.clicked.connect(self.run_check)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Dependency Health · ตรวจเฉพาะบริการ local และโฟลเดอร์แอป"))
        layout.addWidget(self._summary)
        layout.addWidget(self._refresh, alignment=Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(self._table)
    def run_check(self) -> None:
        self._refresh.setEnabled(False)
        self._summary.setText("กำลังตรวจ dependency… การตรวจอาจใช้เวลาสูงสุดประมาณ 5 วินาที")
        from PySide6.QtWidgets import QApplication

        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            checks = collect_runtime_health()
        except Exception as exc:  # Keep diagnostics from taking down the workbench.
            checks = [RuntimeCheck("Health check", "ERROR", str(exc))]
        finally:
            QApplication.restoreOverrideCursor()
        self._table.setRowCount(0)
        ready = 0
        for check in checks:
            row = self._table.rowCount()
            self._table.insertRow(row)
            for column, value in enumerate((check.component, check.status, check.details)):
                item = QTableWidgetItem(value)
                item.setToolTip(value)
                if column == 1:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self._table.setItem(row, column, item)
            ready += check.status == "READY"
        self._summary.setText(f"พร้อม {ready}/{len(checks)} รายการ · สถานะ dependency ไม่ใช่ผล PASS ของเกม")
        self._refresh.setEnabled(True)

