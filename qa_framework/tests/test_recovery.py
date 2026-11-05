"""Tests for self-healing recovery primitives."""

from __future__ import annotations

import os
import sys
import traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from qa_framework.recovery import (
    RecoveryAction,
    RecoveryManager,
    RecoveryResult,
)


def test_recovery_manager_default_state():
    """RecoveryManager starts with zero counts."""
    rm = RecoveryManager()
    assert rm._retry_count == 0
    assert rm._relaunch_count == 0
    assert len(rm.log) == 0


def test_recovery_manager_reset():
    """Reset clears all counters."""
    rm = RecoveryManager()
    rm._retry_count = 2
    rm._relaunch_count = 1
    rm.reset()
    assert rm._retry_count == 0
    assert rm._relaunch_count == 0


def test_recoverable_oserror():
    """OSError is recoverable."""
    rm = RecoveryManager()
    assert rm.is_recoverable(OSError("test")) is True


def test_recoverable_timeout():
    """subprocess.TimeoutExpired is recoverable."""
    import subprocess
    rm = RecoveryManager()
    assert rm.is_recoverable(subprocess.TimeoutExpired("cmd", 1)) is True


def test_recoverable_process_lookup():
    """ProcessLookupError is recoverable."""
    rm = RecoveryManager()
    assert rm.is_recoverable(ProcessLookupError("test")) is True


def test_recoverable_connection_error():
    """ConnectionError is recoverable."""
    rm = RecoveryManager()
    assert rm.is_recoverable(ConnectionError("test")) is True


def test_unrecoverable_assertion():
    """AssertionError is not recoverable."""
    rm = RecoveryManager()
    assert rm.is_recoverable(AssertionError("test")) is False


def test_unrecoverable_value_error():
    """ValueError is not recoverable."""
    rm = RecoveryManager()
    assert rm.is_recoverable(ValueError("bad input")) is False


def test_retry_first():
    """First recovery attempt is RETRY."""
    rm = RecoveryManager()
    result = rm.recover(OSError("test"))
    assert result.action == RecoveryAction.RETRY
    assert result.success is True
    assert rm._retry_count == 1


def test_escalate_after_max_retries():
    """After max retries, escalate (no callbacks)."""
    rm = RecoveryManager(max_retries=2, retry_delay=0.1)
    for _ in range(3):
        result = rm.recover(OSError("test"))
    assert result.action == RecoveryAction.ESCALATE


def test_relaunch_after_retries():
    """Relaunch fires after retries exhausted when callback provided."""
    rm = RecoveryManager(max_retries=1, retry_delay=0.1)
    rm.recover(OSError("test"))  # retry 1
    result = rm.recover(
        OSError("test"),
        relaunch_fn=lambda: True,
    )
    assert result.action == RecoveryAction.RELAUNCH
    assert result.success is True


def test_relaunch_failure():
    """Relaunch with failing callback."""
    rm = RecoveryManager(max_retries=1, retry_delay=0.1)
    rm.recover(OSError("test"))  # retry
    result = rm.recover(
        OSError("test"),
        relaunch_fn=lambda: False,
    )
    assert result.action == RecoveryAction.RELAUNCH
    assert result.success is False


def test_relaunch_exception():
    """Relaunch callback that raises exception."""
    rm = RecoveryManager(max_retries=1, retry_delay=0.1)
    rm.recover(OSError("test"))  # retry
    result = rm.recover(
        OSError("test"),
        relaunch_fn=lambda: 1 / 0,  # raises ZeroDivisionError
    )
    assert result.action == RecoveryAction.RELAUNCH
    assert result.success is False


def test_state_reset_callback():
    """State reset callback is called."""
    rm = RecoveryManager(max_retries=0, retry_delay=0.1)
    called = []
    result = rm.recover(
        OSError("test"),
        state_reset_fn=lambda: called.append(True) or True,
    )
    assert result.action == RecoveryAction.STATE_RESET
    assert len(called) == 1


def test_fallback_input_callback():
    """Fallback input callback is called."""
    rm = RecoveryManager(max_retries=0, retry_delay=0.1)
    called = []
    result = rm.recover(
        OSError("test"),
        fallback_input_fn=lambda: called.append(True) or True,
    )
    assert result.action == RecoveryAction.FALLBACK_INPUT
    assert len(called) == 1


def test_unrecoverable_skips_to_escalate():
    """Unrecoverable error goes straight to ESCALATE."""
    rm = RecoveryManager()
    result = rm.recover(ValueError("bad input"))
    assert result.action == RecoveryAction.ESCALATE
    assert result.success is False


def test_recovery_log_tracks_all_actions():
    """Recovery log contains all actions taken."""
    rm = RecoveryManager(max_retries=1, retry_delay=0.1)
    rm.recover(OSError("test"))
    rm.recover(OSError("test"))
    log = rm.log
    assert len(log) >= 2
    assert all("action" in entry for entry in log)


def test_recovery_result_to_dict():
    """RecoveryResult.to_dict() returns expected structure."""
    result = RecoveryResult(
        action=RecoveryAction.RETRY,
        success=True,
        elapsed=1.5,
        context={"attempt": 1},
    )
    d = result.to_dict()
    assert d["action"] == "retry"
    assert d["success"] is True
    assert d["elapsed"] == 1.5


def test_kill_process_nonexistent():
    """kill_process returns False for non-existent PID."""
    rm = RecoveryManager()
    assert rm.kill_process(999999) is False


def test_launch_process():
    """launch_process returns a Popen instance."""
    import sys
    rm = RecoveryManager()
    proc = rm.launch_process([sys.executable, "-c", "pass"])
    proc.wait(timeout=10)
    assert proc.poll() == 0


def test_relaunch_counters_increment():
    """Relaunch counter increments on each relaunch attempt."""
    rm = RecoveryManager(max_retries=0, retry_delay=0.1)
    rm.recover(OSError("test"), relaunch_fn=lambda: True)
    assert rm._relaunch_count == 1
    rm.recover(OSError("test"), relaunch_fn=lambda: True)
    assert rm._relaunch_count == 2


def test_max_relaunches_cap():
    """Relaunch stops after max_relaunches."""
    rm = RecoveryManager(max_retries=0, retry_delay=0.1, max_relaunches=1)
    rm.recover(OSError("test"), relaunch_fn=lambda: False)
    rm.recover(OSError("test"), relaunch_fn=lambda: False)
    # After max relaunches, next recovery should go to state_reset or escalate
    result = rm.recover(OSError("test"), state_reset_fn=lambda: True)
    assert result.action == RecoveryAction.STATE_RESET


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    passed = 0
    failed = 0
    for t in tests:
        try:
            t()
            passed += 1
            print(f"PASS: {t.__name__}")
        except Exception as e:
            failed += 1
            print(f"FAIL: {t.__name__}: {e}")
            traceback.print_exc()
    print(f"\n{passed} passed, {failed} failed")
