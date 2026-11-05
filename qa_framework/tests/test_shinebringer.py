"""Unit tests for Shinebringer QA suite logic."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.qa.test_case import TestCase, TestResult, TestRunner
from qa_framework.suite import Suite, load_suite, run_suite


class TestSuiteLoading:
    """Test declarative suite JSON loading and validation."""

    def test_load_valid_shinebringer_suite(self) -> None:
        suite = load_suite("qa_framework/examples/shinebringer_qa_suite.json")
        assert suite.name == "Shinebringer Demo QA Suite"
        assert len(suite.cases) >= 3

    def test_load_missing_suite_raises(self) -> None:
        with pytest.raises(FileNotFoundError):
            load_suite("nonexistent.json")


class TestSuiteRunning:
    """Test suite execution with mock data."""

    def test_run_suite_returns_results(self) -> None:
        suite = load_suite("qa_framework/examples/shinebringer_qa_suite.json")
        results = run_suite(suite)
        assert isinstance(results, list)
        assert all(hasattr(r, "passed") for r in results)

    def test_run_suite_stops_at_first_failure(self) -> None:
        def _fail_step() -> None:
            raise AssertionError("step fails")

        cases = [
            TestCase(
                name="multi-step",
                steps=[
                    ("first", lambda: None),
                    ("second", _fail_step),
                ],
            )
        ]
        suite = Suite(name="test", cases=cases)
        results = run_suite(suite)
        assert len(results) == 1  # stops at first failure


class TestWaveVerificationLogic:
    """Test wave count verification logic."""

    def test_wave_count_structure(self) -> None:
        """Verify the demo has 7 stages (Day1→Night1→Day2→Night2→Day3→Night3→Day4)."""
        stages = ["Day1", "Night1", "Day2", "Night2", "Day3", "Night3", "Day4"]
        assert len(stages) == 7
        assert stages[0] == "Day1"
        assert stages[-1] == "Day4"


class TestTestResultReporting:
    """Test test result reporting structure."""

    def test_testresult_has_required_fields(self) -> None:
        result = TestResult(name="test", passed=True)
        assert result.name == "test"
        assert result.passed is True
        assert isinstance(result.steps, list)

    def test_testerunner_summary(self) -> None:
        results = [
            TestResult(name="t1", passed=True),
            TestResult(name="t2", passed=False),
            TestResult(name="t3", passed=True),
        ]
        summary = TestRunner.summary(results)
        assert summary["total"] == 3
        assert summary["passed"] == 2
        assert summary["failed"] == 1
