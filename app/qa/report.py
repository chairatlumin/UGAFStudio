from __future__ import annotations

from datetime import datetime
from html import escape
from pathlib import Path

from app.qa.test_case import TestResult
from app.utils.file import ensure_directory, unique_path


class ReportGenerator:
    """Generates standalone HTML test reports."""

    def generate(self, results: list[TestResult], output_dir: Path) -> Path:
        """Write an HTML report and return its path."""
        ensure_directory(output_dir)

        path = unique_path(output_dir, "test_report", "html")
        path.write_text(self.to_html(results), encoding="utf-8")

        return path

    def to_html(self, results: list[TestResult]) -> str:
        """Render test results as an HTML document."""
        passed = sum(1 for result in results if result.passed)
        failed = sum(1 for result in results if not result.passed)

        rows = "\n".join(_result_rows(result) for result in results)

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>UGAF Studio Test Report</title>
<style>
body {{ font-family: sans-serif; margin: 2rem; }}
.summary {{ display: flex; gap: 2rem; margin-bottom: 2rem; }}
.pill {{ padding: 0.5rem 1rem; border-radius: 4px; color: #fff; }}
.pass {{ background: #2e7d32; }}
.fail {{ background: #c62828; }}
.total {{ background: #1565c0; }}
table {{ border-collapse: collapse; width: 100%; }}
th, td {{ border: 1px solid #ccc; padding: 0.5rem; text-align: left; }}
.passed-row {{ background: #e8f5e9; }}
.failed-row {{ background: #ffebee; }}
</style>
</head>
<body>
<h1>UGAF Studio Test Report</h1>
<p>Generated {escape(datetime.now().isoformat())}</p>
<div class="summary">
<div class="pill total">Total: {len(results)}</div>
<div class="pill pass">Passed: {passed}</div>
<div class="pill fail">Failed: {failed}</div>
</div>
<table>
<tr><th>Test</th><th>Status</th><th>Duration (ms)</th><th>Step</th><th>Message</th></tr>
{rows}
</table>
</body>
</html>"""


def _result_rows(result: TestResult) -> str:
    if not result.steps:
        return _row(result.name, result.passed, result.duration_ms, "-", "")

    return "\n".join(
        _row(
            result.name,
            result.passed,
            result.duration_ms,
            step.name,
            step.message,
        )
        for step in result.steps
    )


def _row(name: str, passed: bool, duration_ms: float, step: str, message: str) -> str:
    css = "passed-row" if passed else "failed-row"
    status = "PASS" if passed else "FAIL"

    return (
        f'<tr class="{css}"><td>{escape(name)}</td>'
        f"<td>{status}</td>"
        f"<td>{duration_ms:.1f}</td>"
        f"<td>{escape(step)}</td>"
        f"<td>{escape(message)}</td></tr>"
    )
