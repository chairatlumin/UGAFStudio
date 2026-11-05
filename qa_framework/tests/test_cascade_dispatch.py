"""Tests for CascadeDispatchRouter and EscalationPolicy."""
from __future__ import annotations

from qa_framework.cascade_dispatch import CascadeDispatchRouter, EscalationPolicy


def test_escalation_min_output_length() -> None:
    policy = EscalationPolicy(min_output_length=10)
    assert policy.should_escalate("short", "model") is True
    assert policy.should_escalate("long enough output", "model") is False


def test_escalation_require_json() -> None:
    policy = EscalationPolicy(require_json=True)
    assert policy.should_escalate("not json", "model") is True
    assert policy.should_escalate('{"key": "value"}', "model") is False


def test_escalation_forbidden_terms() -> None:
    policy = EscalationPolicy(forbidden_terms=["error", "fail"])
    assert policy.should_escalate("there is an error here", "model") is True
    assert policy.should_escalate("success case", "model") is False


def test_router_escalates_on_consecutive_failures() -> None:
    router = CascadeDispatchRouter(models=["small", "large"])
    router.record_result("small", "short")
    assert router.current_model == "small"
    router.record_result("small", "x")
    assert router.current_model == "large"


def test_router_no_escalation_on_success() -> None:
    router = CascadeDispatchRouter(models=["small", "large"])
    router.record_result("small", "long enough output with substance")
    assert router.current_model == "small"
    assert router.cost_report()["escalation_count"] == 0


def test_cost_report_tracking() -> None:
    router = CascadeDispatchRouter(models=["a", "b", "c"])
    router.record_result("a", "x")  # failure, failure_counts["a"] = 1
    router.record_result("a", "x")  # failure, failure_counts["a"] = 2, escalate
    report = router.cost_report()
    assert report["total_dispatches"] == 2
    assert report["escalation_count"] == 1
    assert report["current_model"] == "b"


def test_connection_error_escalation() -> None:
    router = CascadeDispatchRouter(models=["small", "large"])
    router.record_connection_error("small")
    assert router.current_model == "large"
    assert router.cost_report()["escalation_count"] == 1
