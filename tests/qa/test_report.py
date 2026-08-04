from __future__ import annotations

from pathlib import Path

from app.qa.report import ReportGenerator
from app.qa.test_case import TestCase, TestResult


def test_report_writes_html(tmp_path: Path) -> None:
    cases = [
        TestCase(name="passing", steps=[("ok", lambda: None)]),
        TestCase(name="failing", steps=[("bad", lambda: _fail())]),
    ]
    results = [case.run() for case in cases]

    path = ReportGenerator().generate(results, tmp_path)

    assert path.exists()
    content = path.read_text(encoding="utf-8")

    assert "UGAF Studio Test Report" in content
    assert "Passed: 1" in content
    assert "Failed: 1" in content
    assert "PASS" in content
    assert "FAIL" in content


def test_report_renders_rows() -> None:
    results = [TestResult(name="demo", passed=True, duration_ms=5.0)]

    html = ReportGenerator().to_html(results)

    assert "demo" in html
    assert "5.0" in html


def _fail() -> None:
    raise AssertionError("boom")
