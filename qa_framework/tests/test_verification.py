"""Tests for verification layer."""

from __future__ import annotations

import os
import sys

import numpy as np

# Ensure qa_framework is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from qa_framework.verification import (
    Checkpoint,
    QARun,
    frame_diff,
    process_alive,
)


def test_process_alive_current_pid():
    """process_alive returns True for the current process."""
    assert process_alive(os.getpid()) is True


def test_process_alive_fake_pid():
    """process_alive returns False for a non-existent PID."""
    assert process_alive(999999) is False


def test_checkpoint_passes():
    """Checkpoint with trivial True condition passes immediately."""
    cp = Checkpoint(name="pass", condition=lambda: True, timeout=1.0)
    assert cp.check() is True
    assert cp.result is True


def test_checkpoint_fails():
    """Checkpoint with always-False condition fails after timeout."""
    cp = Checkpoint(name="fail", condition=lambda: False, timeout=0.5)
    assert cp.check() is False
    assert cp.result is False


def test_qarun_passes():
    """QARun with all-passing checkpoints returns True."""
    qar = QARun(
        name="test",
        checkpoints=[
            Checkpoint(name="c1", condition=lambda: True, timeout=1.0),
            Checkpoint(name="c2", condition=lambda: True, timeout=1.0),
        ],
    )
    assert qar.run() is True
    assert qar.result == "passed"


def test_qarun_fails_at_required():
    """QARun fails when a required checkpoint fails."""
    qar = QARun(
        name="test",
        checkpoints=[
            Checkpoint(name="pass", condition=lambda: True, timeout=1.0),
            Checkpoint(name="fail", condition=lambda: False, timeout=0.5),
        ],
    )
    assert qar.run() is False
    assert "fail" in qar.result


def test_qarun_optional_checkpoint():
    """QARun continues past optional (non-required) checkpoint failures."""
    qar = QARun(
        name="test",
        checkpoints=[
            Checkpoint(
                name="fail_opt",
                condition=lambda: False,
                timeout=0.5,
                required=False,
            ),
            Checkpoint(name="pass", condition=lambda: True, timeout=1.0),
        ],
    )
    assert qar.run() is True


def test_qarun_report_structure():
    """QARun.report() returns expected keys."""
    qar = QARun(
        name="report_test",
        checkpoints=[Checkpoint(name="c1", condition=lambda: True, timeout=1.0)],
    )
    qar.run()
    report = qar.report()
    assert "name" in report
    assert "result" in report
    assert "checkpoints" in report
    assert "c1" in report["checkpoints"]


def test_frame_diff_identical():
    """frame_diff returns False for identical frames."""
    frame = np.zeros((100, 100, 3), dtype=np.uint8)
    assert frame_diff(frame, frame) is False


def test_frame_diff_different():
    """frame_diff returns True for completely different frames."""
    a = np.zeros((100, 100, 3), dtype=np.uint8)
    b = np.ones((100, 100, 3), dtype=np.uint8) * 255
    assert frame_diff(a, b) is True


def test_frame_diff_none():
    """frame_diff returns False when either frame is None."""
    frame = np.zeros((100, 100, 3), dtype=np.uint8)
    assert frame_diff(None, frame) is False
    assert frame_diff(frame, None) is False
    assert frame_diff(None, None) is False


def test_cost_tracker_summary():
    """CostTracker.summary() returns expected structure."""
    from qa_framework.metrics import CostTracker
    ct = CostTracker()
    ct.log("cp1", tokens=100, cost_usd=0.001)
    ct.log("cp2", tokens=200, cost_usd=0.002)
    s = ct.summary()
    assert s["total_tokens"] == 300
    assert s["checkpoints_logged"] == 2


if __name__ == "__main__":
    # Simple runner if pytest not available
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
