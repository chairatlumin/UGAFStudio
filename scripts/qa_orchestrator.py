"""Unified QA Orchestrator — runs single suites, combined suites, and unit tests.

Aggregates results across all runs into a single HTML report with pass/fail
summary, per-game breakdown, and embedded screenshots.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

from qa_framework.gameplay.coordinator import run_combined_suite, run_game_by_app_id
from qa_framework.gameplay.report import GameplayReportGenerator
from qa_framework.gameplay.runner import GameplayRunResult


@dataclass
class OrchestratorResult:
    """Aggregated result from all QA runs."""

    game_results: list[GameplayRunResult] = field(default_factory=list)
    unit_test_passed: int = 0
    unit_test_failed: int = 0
    unit_test_errors: int = 0
    duration_seconds: float = 0.0

    @property
    def total_games(self) -> int:
        return len(self.game_results)

    @property
    def games_passed(self) -> int:
        return sum(1 for r in self.game_results if r.passed)

    @property
    def games_failed(self) -> int:
        return self.total_games - self.games_passed

    @property
    def total_assertions(self) -> int:
        return sum(len(r.assertions) for r in self.game_results)

    @property
    def assertions_passed(self) -> int:
        return sum(sum(1 for a in r.assertions if a.passed) for r in self.game_results)

    @property
    def all_passed(self) -> bool:
        return self.games_failed == 0 and self.unit_test_failed == 0 and self.unit_test_errors == 0


def run_unit_tests() -> tuple[int, int, int]:
    """Run pytest and return (passed, failed, errors)."""
    import subprocess

    result = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/", "-q", "--tb=no"],
        capture_output=True,
        text=True,
    )
    output = result.stdout + result.stderr
    passed = failed = errors = 0
    for line in output.splitlines():
        if "passed" in line and "failed" not in line:
            parts = line.split()
            for i, p in enumerate(parts):
                if p == "passed" and i > 0:
                    try:
                        passed = int(parts[i - 1])
                    except ValueError:
                        pass
        if "failed" in line and "passed" not in line:
            parts = line.split()
            for i, p in enumerate(parts):
                if p == "failed" and i > 0:
                    try:
                        failed = int(parts[i - 1])
                    except ValueError:
                        pass
        if "error" in line and "errors" in line:
            parts = line.split()
            for i, p in enumerate(parts):
                if p == "errors" and i > 0:
                    try:
                        errors = int(parts[i - 1])
                    except ValueError:
                        pass
    return passed, failed, errors


def run_single_suite(
    suite_path: Path,
    steam_root: Path | None,
    output_dir: Path,
) -> list[GameplayRunResult]:
    """Run a single game suite."""
    data = json.loads(suite_path.read_text(encoding="utf-8"))
    app_id = data.get("app_id")
    if app_id is None:
        raise ValueError(f"Suite {suite_path} missing 'app_id'")
    result = run_game_by_app_id(
        app_id=app_id,
        suite_path=suite_path,
        steam_root=steam_root,
        output_dir=output_dir,
    )
    return [result]


def run_combined(
    combined_path: Path,
    steam_root: Path | None,
    output_dir: Path,
) -> list[GameplayRunResult]:
    """Run a combined suite."""
    return run_combined_suite(
        combined_path=combined_path,
        steam_root=steam_root,
        output_dir=output_dir,
    )


def generate_aggregate_report(
    result: OrchestratorResult,
    output_dir: Path,
) -> Path:
    """Generate an HTML report aggregating all results."""
    report_gen = GameplayReportGenerator()
    report_gen.generate(result.game_results, output_dir)

    summary_path = output_dir / "orchestrator_summary.html"
    html = _build_summary_html(result, output_dir)
    summary_path.write_text(html, encoding="utf-8")
    return summary_path


def _build_summary_html(result: OrchestratorResult, output_dir: Path) -> str:
    """Build the orchestrator summary HTML."""
    status = "PASS" if result.all_passed else "FAIL"
    status_color = "#2ecc71" if result.all_passed else "#e74c3c"

    game_rows = ""
    for r in result.game_results:
        game_status = "PASS" if r.passed else "FAIL"
        game_color = "#2ecc71" if r.passed else "#e74c3c"
        assertions_text = f"{sum(1 for a in r.assertions if a.passed)}/{len(r.assertions)}"
        game_rows += f"""
        <tr>
            <td>{r.game_name}</td>
            <td>{r.app_id}</td>
            <td style="color:{game_color};font-weight:bold;">{game_status}</td>
            <td>{assertions_text}</td>
            <td>{r.duration_ms:.0f}ms</td>
        </tr>"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>QA Orchestrator Summary</title>
    <style>
        body {{ font-family: system-ui, sans-serif; margin: 2rem;
               background: #1a1a2e; color: #eee; }}
        h1 {{ color: #fff; }}
        .summary {{ background: #16213e; padding: 1.5rem;
                    border-radius: 8px; margin: 1rem 0; }}
        .metric {{ display: inline-block; margin: 0.5rem 1rem; }}
        .metric-value {{ font-size: 2rem; font-weight: bold; }}
        .status-pass {{ color: #2ecc71; }}
        .status-fail {{ color: #e74c3c; }}
        table {{ width: 100%; border-collapse: collapse; margin: 1rem 0; }}
        th, td {{ padding: 0.75rem; text-align: left;
                  border-bottom: 1px solid #333; }}
        th {{ background: #0f3460; }}
        tr:hover {{ background: #1a1a3e; }}
    </style>
</head>
<body>
    <h1>QA Orchestrator Summary</h1>
    <div class="summary">
        <div class="metric">
            <div class="metric-value" style="color:{status_color};">{status}</div>
            <div>Overall</div>
        </div>
        <div class="metric">
            <div class="metric-value">
                {result.games_passed}/{result.total_games}
            </div>
            <div>Games Passed</div>
        </div>
        <div class="metric">
            <div class="metric-value">
                {result.assertions_passed}/{result.total_assertions}
            </div>
            <div>Assertions Passed</div>
        </div>
        <div class="metric">
            <div class="metric-value">
                {result.unit_test_passed}/
                {result.unit_test_passed + result.unit_test_failed}
            </div>
            <div>Unit Tests Passed</div>
        </div>
        <div class="metric">
            <div class="metric-value">{result.duration_seconds:.1f}s</div>
            <div>Duration</div>
        </div>
    </div>

    <h2>Game Results</h2>
    <table>
        <thead>
            <tr><th>Game</th><th>App ID</th><th>Status</th><th>Assertions</th><th>Duration</th></tr>
        </thead>
        <tbody>
            {game_rows if game_rows else '<tr><td colspan="5">No games run</td></tr>'}
        </tbody>
    </table>
</body>
</html>"""


def main() -> int:
    parser = argparse.ArgumentParser(description="UGAF Unified QA Orchestrator")
    parser.add_argument("--suite", help="Path to a single game suite JSON")
    parser.add_argument("--combined", help="Path to a combined suite JSON")
    parser.add_argument("--steam-root", help="Override Steam library root")
    parser.add_argument("--output-dir", default="reports", help="Output directory")
    parser.add_argument("--skip-unit-tests", action="store_true", help="Skip unit test run")
    parser.add_argument("--skip-gameplay", action="store_true", help="Skip gameplay QA")
    args = parser.parse_args()

    if not args.suite and not args.combined:
        parser.error("Provide --suite or --combined")

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    steam_root = Path(args.steam_root) if args.steam_root else None

    start = time.monotonic()
    result = OrchestratorResult()

    # Run unit tests
    if not args.skip_unit_tests:
        print("Running unit tests...")
        passed, failed, errors = run_unit_tests()
        result.unit_test_passed = passed
        result.unit_test_failed = failed
        result.unit_test_errors = errors
        print(f"  Unit tests: {passed} passed, {failed} failed, {errors} errors")

    # Run gameplay QA
    if not args.skip_gameplay:
        if args.suite:
            print(f"Running single suite: {args.suite}")
            game_results = run_single_suite(Path(args.suite), steam_root, output_dir)
            result.game_results.extend(game_results)
        elif args.combined:
            print(f"Running combined suite: {args.combined}")
            game_results = run_combined(Path(args.combined), steam_root, output_dir)
            result.game_results.extend(game_results)

        for r in result.game_results:
            status = "PASS" if r.passed else "FAIL"
            passed = sum(1 for a in r.assertions if a.passed)
            total = len(r.assertions)
            print(f"  {r.game_name} ({r.app_id}): {status} — {passed}/{total} assertions")

    result.duration_seconds = time.monotonic() - start

    # Generate report
    summary_path = generate_aggregate_report(result, output_dir)
    print(f"\nReport: {summary_path}")
    print(f"Overall: {'PASS' if result.all_passed else 'FAIL'}")
    return 0 if result.all_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
