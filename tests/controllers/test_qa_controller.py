from __future__ import annotations

from pathlib import Path

from app.controllers.qa_controller import QAController
from app.qa.test_case import TestRunner


def test_run_demo_returns_passing_suite() -> None:
    results = QAController().run_demo()

    assert len(results) == 2
    assert all(result.passed for result in results)

    summary = TestRunner.summary(results)

    assert summary["passed"] == 2
    assert summary["failed"] == 0


def test_generate_report_writes_html(tmp_path: Path) -> None:
    controller = QAController()
    results = controller.run_demo()

    path = controller.generate_report(results, tmp_path)

    assert path.exists()
    assert "UGAF Studio Test Report" in path.read_text(encoding="utf-8")
