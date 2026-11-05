"""Tests for StatisticalTestRunner."""
from __future__ import annotations

from qa_framework.statistical_runner import StatisticalTestRunner


class DummyRunner:
    def run_all(self):
        return [{"success": True}]


class FailingRunner:
    def run_all(self):
        return [{"success": False}]


def test_pass_rate() -> None:
    runner = StatisticalTestRunner(runs=5)
    result = runner.run(DummyRunner())
    assert result["total_runs"] == 5
    assert result["passes"] == 5
    assert result["pass_rate"] == 1.0
    assert result["passed"] is True


def test_failure_rate() -> None:
    runner = StatisticalTestRunner(runs=5)
    result = runner.run(FailingRunner())
    assert result["total_runs"] == 5
    assert result["passes"] == 0
    assert result["pass_rate"] == 0.0
    assert result["passed"] is False


def test_confidence_interval() -> None:
    runner = StatisticalTestRunner(runs=10, confidence=0.95)
    result = runner.run(DummyRunner())
    assert "confidence_interval" in result
    ci_low, ci_high = result["confidence_interval"]
    assert 0.0 <= ci_low <= ci_high <= 1.0


def test_threshold_enforcement() -> None:
    runner = StatisticalTestRunner(runs=10, pass_threshold=0.5)
    result = runner.run(DummyRunner())
    assert result["passed"] is True

    runner2 = StatisticalTestRunner(runs=10, pass_threshold=0.9)
    result2 = runner2.run(DummyRunner())
    assert result2["passed"] is True

    runner3 = StatisticalTestRunner(runs=10, pass_threshold=1.0)
    result3 = runner3.run(FailingRunner())
    assert result3["passed"] is False


def test_zero_runs_edge_case() -> None:
    runner = StatisticalTestRunner(runs=0)
    result = runner.run(lambda: None)  # type: ignore
    assert result["total_runs"] == 0
    assert result["pass_rate"] == 0.0
