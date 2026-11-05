"""Tests for QA Orchestrator CLI."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from qa_framework.gameplay.assertions import AssertionResult
from qa_framework.gameplay.runner import GameplayRunResult
from scripts.qa_orchestrator import OrchestratorResult, generate_aggregate_report


def _make_result(**kwargs: Any) -> GameplayRunResult:
    """Create a GameplayRunResult with sensible defaults."""
    defaults: dict[str, Any] = {
        "game_name": "Test",
        "app_id": 1,
        "install_path": "/test",
        "started": True,
        "startup_error": None,
        "cleanup": None,
        "screenshot_path": None,
        "assertions": [],
        "duration_ms": 0.0,
    }
    defaults.update(kwargs)
    return GameplayRunResult(**defaults)


class TestOrchestratorResult:
    def test_total_games_empty(self) -> None:
        result = OrchestratorResult()
        assert result.total_games == 0

    def test_total_games_count(self) -> None:
        result = OrchestratorResult(game_results=[_make_result(), _make_result(app_id=2)])
        assert result.total_games == 2

    def test_games_passed(self) -> None:
        result = OrchestratorResult(
            game_results=[
                _make_result(
                    game_name="Passing",
                    assertions=[AssertionResult(name="a", passed=True, message="ok")],
                ),
                _make_result(
                    game_name="Failing",
                    app_id=2,
                    assertions=[AssertionResult(name="a", passed=False, message="fail")],
                ),
            ]
        )
        assert result.games_passed == 1
        assert result.games_failed == 1

    def test_all_passed_true(self) -> None:
        result = OrchestratorResult(
            game_results=[_make_result()],
            unit_test_passed=10,
            unit_test_failed=0,
        )
        assert result.all_passed is True

    def test_all_passed_false_with_failed_tests(self) -> None:
        result = OrchestratorResult(
            unit_test_passed=10,
            unit_test_failed=2,
        )
        assert result.all_passed is False

    def test_assertions_count(self) -> None:
        result = OrchestratorResult(
            game_results=[
                _make_result(
                    assertions=[
                        AssertionResult(name="a", passed=True, message=""),
                        AssertionResult(name="b", passed=False, message=""),
                        AssertionResult(name="c", passed=True, message=""),
                    ]
                )
            ]
        )
        assert result.total_assertions == 3
        assert result.assertions_passed == 2


class TestOrchestratorCLI:
    def test_report_generation(self, tmp_path: Path) -> None:
        result = OrchestratorResult(
            game_results=[
                _make_result(
                    game_name="Test Game",
                    app_id=4077460,
                    assertions=[AssertionResult(name="menu", passed=True, message="found")],
                    duration_ms=1500.0,
                )
            ],
            unit_test_passed=267,
            unit_test_failed=0,
            duration_seconds=45.0,
        )

        report_path = generate_aggregate_report(result, tmp_path)
        assert report_path.exists()
        html = report_path.read_text(encoding="utf-8")
        assert "Test Game" in html
        assert "4077460" in html
        assert "PASS" in html

    def test_report_generation_with_failure(self, tmp_path: Path) -> None:
        result = OrchestratorResult(
            game_results=[
                _make_result(
                    game_name="Failing Game",
                    app_id=999,
                    started=False,
                    startup_error="executable not found",
                )
            ],
            unit_test_passed=267,
            unit_test_failed=0,
            duration_seconds=5.0,
        )

        report_path = generate_aggregate_report(result, tmp_path)
        html = report_path.read_text(encoding="utf-8")
        assert "FAIL" in html
