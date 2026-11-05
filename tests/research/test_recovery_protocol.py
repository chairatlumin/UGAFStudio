from __future__ import annotations

from typing import Optional

from qa_framework.research.verification_gates import Gate, GateCondition, GateOperator, GateResult


def test_retry_action():
    """Recovery action 'retry' should be selected for transient failures."""
    from qa_framework.research.recovery_protocol import select_recovery_action
    gate = Gate(name="threshold_check", condition=GateCondition(operator=GateOperator.GT, value=10))
    result = GateResult(gate="threshold_check", passed=False, evidence="value 5 not > 10")
    action = select_recovery_action(gate, result)
    assert action == "retry"


def test_redesign_action():
    """Recovery action 'redesign' should be selected for persistent failures."""
    from qa_framework.research.recovery_protocol import select_recovery_action
    gate = Gate(name="complex_check", condition=GateCondition(operator=GateOperator.GT, value=100))
    result = GateResult(gate="complex_check", passed=False, evidence="complex constraint failed")
    action = select_recovery_action(gate, result)
    assert action == "redesign"


def test_reset_action():
    """Recovery action 'reset' should be selected for critical failures."""
    from qa_framework.research.recovery_protocol import select_recovery_action
    gate = Gate(name="critical_check", condition=GateCondition(operator=GateOperator.EQ, value=0))
    result = GateResult(gate="critical_check", passed=False, evidence="critical state corrupted")
    action = select_recovery_action(gate, result)
    assert action == "reset"


def test_retry_on_gate_lt():
    """Retry action for LT gate failure."""
    from qa_framework.research.recovery_protocol import select_recovery_action
    gate = Gate(name="low_value_check", condition=GateCondition(operator=GateOperator.LT, value=50))
    result = GateResult(gate="low_value_check", passed=False, evidence="value 75 not < 50")
    action = select_recovery_action(gate, result)
    assert action == "retry"


def test_redesign_on_gate_ne():
    """Redesign action for NE gate failure."""
    from qa_framework.research.recovery_protocol import select_recovery_action
    gate = Gate(name="unique_check", condition=GateCondition(operator=GateOperator.NE, value=42))
    result = GateResult(gate="unique_check", passed=False, evidence="value equals 42")
    action = select_recovery_action(gate, result)
    assert action == "redesign"


def test_reset_on_gate_eq_critical():
    """Reset action for EQ gate failure marked critical."""
    from qa_framework.research.recovery_protocol import select_recovery_action
    gate = Gate(name="state_check", condition=GateCondition(operator=GateOperator.EQ, value=0))
    result = GateResult(gate="state_check", passed=False, evidence="state corrupted")
    action = select_recovery_action(gate, result)
    assert action == "reset"