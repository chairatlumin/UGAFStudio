from __future__ import annotations

from datetime import datetime
from html import escape
from pathlib import Path

from app.utils.file import ensure_directory, unique_path
from qa_framework.gameplay.runner import GameplayRunResult


class GameplayReportGenerator:
    """Renders gameplay QA runs as standalone HTML reports."""

    def generate(
        self,
        runs: list[GameplayRunResult],
        output_dir: Path = Path("reports"),
    ) -> Path:
        """Write an HTML report covering one or more game runs."""
        ensure_directory(output_dir)
        path = unique_path(output_dir, "gameplay_report", "html")
        path.write_text(self.to_html(runs), encoding="utf-8")
        for run in runs:
            run.report_path = path
        return path

    def to_html(self, runs: list[GameplayRunResult]) -> str:
        """Render the runs as an HTML document."""
        generated = escape(datetime.now().isoformat())
        body_rows = "\n".join(_game_section(run) for run in runs)

        overall_passed = sum(1 for run in runs if run.passed)
        overall_failed = len(runs) - overall_passed

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>UGAF Studio Gameplay QA Report</title>
<style>
body {{ font-family: sans-serif; margin: 2rem; }}
.summary {{ display: flex; gap: 2rem; margin-bottom: 2rem; }}
.pill {{ padding: 0.5rem 1rem; border-radius: 4px; color: #fff; }}
.pass {{ background: #2e7d32; }}
.fail {{ background: #c62828; }}
.total {{ background: #1565c0; }}
.game {{ border: 1px solid #ccc; border-radius: 6px; padding: 1rem; margin-bottom: 1.5rem; }}
.meta {{ list-style: none; padding: 0; }}
.meta li {{ margin: 0.2rem 0; }}
.passed {{ color: #2e7d32; }}
.failed {{ color: #c62828; }}
table {{ border-collapse: collapse; width: 100%; margin-top: 0.5rem; }}
th, td {{ border: 1px solid #ccc; padding: 0.4rem; text-align: left; }}
.assert-pass {{ background: #e8f5e9; }}
.assert-fail {{ background: #ffebee; }}
</style>
</head>
<body>
<h1>UGAF Studio Gameplay QA Report</h1>
<p>Generated {generated}</p>
<div class="summary">
<div class="pill total">Games: {len(runs)}</div>
<div class="pill pass">Passed: {overall_passed}</div>
<div class="pill fail">Failed: {overall_failed}</div>
</div>
{body_rows}
</body>
</html>"""


def _game_section(run: GameplayRunResult) -> str:
    status = "PASS" if run.passed else "FAIL"
    status_class = "passed" if run.passed else "failed"

    cleanup = run.cleanup
    if cleanup is None:
        cleanup_text = "n/a"
    else:
        note = f" ({escape(cleanup.note)})" if cleanup.note else ""
        cleanup_text = f"{escape(cleanup.status)}{note}"

    screenshot_text = escape(str(run.screenshot_path)) if run.screenshot_path else "none"
    report_text = escape(str(run.report_path)) if run.report_path else "pending"
    executable_text = escape(str(run.executable)) if run.executable else "not launched"
    pid_text = str(run.pid) if run.pid is not None else "n/a"
    bot_text = "not enabled"
    if run.bot is not None:
        bot_text = (
            f"{'PASS' if run.bot.passed else 'FAIL'}; steps={run.bot.steps}; "
            f"actions={escape(', '.join(run.bot.actions)) or 'none'}"
        )
        if run.bot.error:
            bot_text += f"; error={escape(run.bot.error)}"

    assertions_rows = (
        "\n".join(
            f'<tr class="{"assert-pass" if a.passed else "assert-fail"}">'
            f"<td>{escape(a.name)}</td>"
            f"<td>{'PASS' if a.passed else 'FAIL'}</td>"
            f"<td>{escape(a.message)}</td></tr>"
            for a in run.assertions
        )
        or '<tr><td colspan="3">No visual assertions configured.</td></tr>'
    )

    return f"""<div class="game">
<h2 class="{status_class}">{escape(run.game_name)} — {status}</h2>
<ul class="meta">
<li><strong>App ID:</strong> {run.app_id}</li>
<li><strong>Install path:</strong> {escape(run.install_path)}</li>
<li><strong>Executable:</strong> {executable_text}</li>
<li><strong>PID:</strong> {pid_text}</li>
<li><strong>Autonomous bot:</strong> {bot_text}</li>
<li><strong>Starts up:</strong> {"yes" if run.started else "no"}</li>
<li><strong>Startup error:</strong> {escape(run.startup_error or "none")}</li>
<li><strong>Process cleanup:</strong> {cleanup_text}</li>
<li><strong>Screenshot:</strong> {screenshot_text}</li>
<li><strong>Duration:</strong> {run.duration_ms:.1f} ms</li>
<li><strong>Report path:</strong> {report_text}</li>
</ul>
<table>
<tr><th>Assertion</th><th>Status</th><th>Message</th></tr>
{assertions_rows}
</table>
</div>"""
