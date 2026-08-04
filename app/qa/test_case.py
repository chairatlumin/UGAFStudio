from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable


@dataclass
class StepResult:
    """Outcome of a single test step."""

    name: str
    passed: bool
    message: str = ""
    duration_ms: float = 0.0


@dataclass
class TestResult:
    """Outcome of a test case."""

    name: str
    passed: bool
    duration_ms: float = 0.0
    steps: list[StepResult] = field(default_factory=list)


class TestCase:
    """Runs a sequence of named steps, stopping at the first failure.

    Steps are callables that raise AssertionError on failure.
    """

    def __init__(self, name: str, steps: list[tuple[str, Callable[[], None]]]) -> None:
        self.name = name
        self.steps = steps

    def run(self) -> TestResult:
        """Execute all steps and return the result."""
        results: list[StepResult] = []

        started = time.perf_counter()

        for name, action in self.steps:
            step_started = time.perf_counter()

            step, passed = _run_step(name, action)

            step.duration_ms = (time.perf_counter() - step_started) * 1000.0
            results.append(step)

            if not passed:
                break

        return TestResult(
            name=self.name,
            passed=all(result.passed for result in results),
            duration_ms=(time.perf_counter() - started) * 1000.0,
            steps=results,
        )


def _run_step(name: str, action: Callable[[], None]) -> tuple[StepResult, bool]:
    try:
        action()
    except AssertionError as exc:
        return StepResult(name=name, passed=False, message=str(exc)), False
    except Exception as exc:
        return StepResult(name=name, passed=False, message=f"error: {exc}"), False

    return StepResult(name=name, passed=True), True


class TestRunner:
    """Runs test cases and produces summaries."""

    def run(self, cases: list[TestCase]) -> list[TestResult]:
        """Run every test case in order."""
        return [case.run() for case in cases]

    @staticmethod
    def summary(results: list[TestResult]) -> dict[str, int]:
        """Return aggregate pass/fail counts."""
        return {
            "total": len(results),
            "passed": sum(1 for result in results if result.passed),
            "failed": sum(1 for result in results if not result.passed),
        }
