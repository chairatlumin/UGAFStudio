from __future__ import annotations

from PySide6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.qa.test_case import TestResult, TestRunner


class DashboardWidget(QWidget):
    """Displays QA test results and summary counts."""

    def __init__(self) -> None:
        super().__init__()

        self._total = QLabel("Total: 0")
        self._passed = QLabel("Passed: 0")
        self._failed = QLabel("Failed: 0")

        self._table = QTableWidget(0, 3)
        self._table.setHorizontalHeaderLabels(["Test", "Status", "Duration (ms)"])
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)

        self._build_ui()
        self._refresh_summary([])

    def _build_ui(self) -> None:
        summary = QHBoxLayout()
        summary.addWidget(self._total)
        summary.addWidget(self._passed)
        summary.addWidget(self._failed)
        summary.addStretch()

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(summary)
        layout.addWidget(self._table)

        self.setLayout(layout)

    def set_results(self, results: list[TestResult]) -> None:
        """Replace all displayed results."""
        self._table.setRowCount(0)

        for result in results:
            self.append_result(result)

        self._refresh_summary(results)

    def append_result(self, result: TestResult) -> None:
        """Add a single test result to the table."""
        row = self._table.rowCount()
        self._table.insertRow(row)

        self._table.setItem(row, 0, QTableWidgetItem(result.name))
        self._table.setItem(
            row,
            1,
            QTableWidgetItem("PASS" if result.passed else "FAIL"),
        )
        self._table.setItem(row, 2, QTableWidgetItem(f"{result.duration_ms:.1f}"))

    def _refresh_summary(self, results: list[TestResult]) -> None:
        summary = TestRunner.summary(results)

        self._total.setText(f"Total: {summary['total']}")
        self._passed.setText(f"Passed: {summary['passed']}")
        self._failed.setText(f"Failed: {summary['failed']}")

        self._failed.setStyleSheet("color:#ef5350;" if summary["failed"] else "color:#2e7d32;")
