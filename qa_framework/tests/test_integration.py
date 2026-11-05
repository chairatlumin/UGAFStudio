"""Integration tests for verification + recovery + metrics."""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from qa_framework.harness import TraceAggregator
from qa_framework.metrics import RecoveryTracker
from qa_framework.verification import Checkpoint, QARun


def test_recovery_tracker_no_incidents():
    rt = RecoveryTracker()
    assert rt.recovery_rate == 1.0
    assert rt.summary()["incidents"] == 0


def test_recovery_tracker_with_incidents():
    rt = RecoveryTracker()
    rt.record_incident("retry", True)
    rt.record_incident("relaunch", False)
    assert rt.recovery_rate == 0.5
    assert rt.summary()["incidents"] == 2


def test_recovery_tracker_all_success():
    rt = RecoveryTracker()
    rt.record_incident("retry", True)
    rt.record_incident("retry", True)
    assert rt.recovery_rate == 1.0


def test_trace_aggregator_empty():
    with tempfile.TemporaryDirectory() as tmpdir:
        agg = TraceAggregator(log_dir=tmpdir)
        result = agg.aggregate()
        assert result["total_traces"] == 0


def test_trace_aggregator_with_traces():
    with tempfile.TemporaryDirectory() as tmpdir:
        trace = {
            "status": "success",
            "agent_id": "test-agent",
            "game_id": "4077460",
            "task_type": "smoke",
            "elapsed": 1.5,
            "attempts": 1,
            "exit_code": 0,
            "reason": "",
        }
        trace_path = Path(tmpdir) / "trace-20260923-135800-test-agent.json"
        trace_path.write_text(json.dumps(trace), encoding="utf-8")

        agg = TraceAggregator(log_dir=tmpdir)
        result = agg.aggregate()
        assert result["total_traces"] == 1
        assert result["agents"]["test-agent"]["success"] == 1
        assert result["overall"]["success_rate"] == 1.0


def test_trace_aggregator_mixed_status():
    with tempfile.TemporaryDirectory() as tmpdir:
        traces = [
            {
                "status": "success",
                "agent_id": "agent-a",
                "elapsed": 1.0,
                "attempts": 1,
                "exit_code": 0,
                "reason": "",
            },
            {
                "status": "failed",
                "agent_id": "agent-a",
                "elapsed": 2.0,
                "attempts": 3,
                "exit_code": 1,
                "reason": "fail",
            },
            {
                "status": "blocked",
                "agent_id": "agent-b",
                "elapsed": 0.1,
                "attempts": 0,
                "exit_code": None,
                "reason": "blocked",
            },
        ]
        for i, t in enumerate(traces):
            trace_path = Path(tmpdir) / f"trace-20260923-13580{i}-agent.json"
            trace_path.write_text(json.dumps(t), encoding="utf-8")

        agg = TraceAggregator(log_dir=tmpdir)
        result = agg.aggregate()
        assert result["total_traces"] == 3
        assert result["agents"]["agent-a"]["success"] == 1
        assert result["agents"]["agent-a"]["failed"] == 1
        assert result["agents"]["agent-b"]["blocked"] == 1
        assert abs(result["overall"]["success_rate"] - 1/3) < 0.001



def test_qarun_with_recovery_integration():
    """QARun + RecoveryTracker work together."""
    rt = RecoveryTracker()
    qar = QARun(
        name="recovery_test",
        checkpoints=[Checkpoint(name="fail", condition=lambda: False, timeout=0.3)],
    )
    result = qar.run()
    rt.record_incident("retry", result)
    assert rt.recovery_rate == 0.0
    assert qar.result == "failed:fail"


def test_qarun_passes_immediately():
    """QARun with all True conditions passes."""
    qar = QARun(
        name="fast_pass",
        checkpoints=[
            Checkpoint(name="c1", condition=lambda: True, timeout=0.5),
            Checkpoint(name="c2", condition=lambda: True, timeout=0.5),
        ],
    )
    assert qar.run() is True
    assert qar.result == "passed"


def test_recovery_tracker_summary_format():
    rt = RecoveryTracker()
    rt.record_incident("retry", True)
    s = rt.summary()
    assert "incidents" in s
    assert "recoveries" in s
    assert "recovery_rate" in s
    assert "actions" in s
    assert len(s["actions"]) == 1
    assert s["actions"][0]["action"] == "retry"


if __name__ == "__main__":
    import traceback

    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    passed = 0
    failed = 0
    for t in tests:
        try:
            t()
            passed += 1
            print(f"PASS: {t.__name__}")
        except Exception:
            failed += 1
            print(f"FAIL: {t.__name__}")
            traceback.print_exc()
    print(f"\n{passed} passed, {failed} failed")
