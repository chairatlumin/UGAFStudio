from __future__ import annotations

from app.qa.test_case import TestCase, TestRunner


def test_all_steps_pass() -> None:
    case = TestCase(
        name="smoke",
        steps=[
            ("step one", lambda: None),
            ("step two", lambda: None),
        ],
    )

    result = case.run()

    assert result.passed is True
    assert len(result.steps) == 2
    assert all(step.passed for step in result.steps)


def test_failing_step_stops_execution() -> None:
    order: list[str] = []

    def second_step() -> None:
        order.append("second")
        raise RuntimeError("boom")

    case = TestCase(
        name="failing",
        steps=[
            ("first", lambda: order.append("first")),
            ("second", second_step),
            ("third", lambda: order.append("third")),
        ],
    )

    result = case.run()

    assert result.passed is False
    assert order == ["first", "second"]
    assert result.steps[1].passed is False
    assert "error" in result.steps[1].message


def test_assertion_failure_captures_message() -> None:
    case = TestCase(
        name="assert",
        steps=[("check", lambda: _fail())],
    )

    result = case.run()

    assert result.passed is False
    assert result.steps[0].message == "boom"


def test_runner_and_summary() -> None:
    cases = [
        TestCase(name="a", steps=[("ok", lambda: None)]),
        TestCase(name="b", steps=[("bad", lambda: _fail())]),
    ]

    results = TestRunner().run(cases)
    summary = TestRunner.summary(results)

    assert summary == {"total": 2, "passed": 1, "failed": 1}


def _fail() -> None:
    raise AssertionError("boom")
