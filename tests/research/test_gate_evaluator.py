from __future__ import annotations

from enum import Enum
from typing import Optional

from qa_framework.research.verification_gates import GateOperator, GateCondition, Gate, GateResult


def test_evaluate_eq_true():
    """EQ operator: passed when value equals condition value."""
    from qa_framework.research.gate_evaluator import evaluate_gate
    gate = Gate(name="check", condition=GateCondition(operator=GateOperator.EQ, value=42))
    result = evaluate_gate(gate, 42)
    assert result.passed


def test_evaluate_eq_false():
    """EQ operator: failed when value differs from condition value."""
    from qa_framework.research.gate_evaluator import evaluate_gate
    gate = Gate(name="check", condition=GateCondition(operator=GateOperator.EQ, value=42))
    result = evaluate_gate(gate, 100)
    assert not result.passed


def test_evaluate_ne_true():
    """NE operator: passed when value differs from condition value."""
    from qa_framework.research.gate_evaluator import evaluate_gate
    gate = Gate(name="check", condition=GateCondition(operator=GateOperator.NE, value=42))
    result = evaluate_gate(gate, 100)
    assert result.passed


def test_evaluate_ne_false():
    """NE operator: failed when value equals condition value."""
    from qa_framework.research.gate_evaluator import evaluate_gate
    gate = Gate(name="check", condition=GateCondition(operator=GateOperator.NE, value=42))
    result = evaluate_gate(gate, 42)
    assert not result.passed


def test_evaluate_gt_true():
    """GT operator: passed when value is greater than condition value."""
    from qa_framework.research.gate_evaluator import evaluate_gate
    gate = Gate(name="check", condition=GateCondition(operator=GateOperator.GT, value=10))
    result = evaluate_gate(gate, 20)
    assert result.passed


def test_evaluate_gt_false():
    """GT operator: failed when value is not greater than condition value."""
    from qa_framework.research.gate_evaluator import evaluate_gate
    gate = Gate(name="check", condition=GateCondition(operator=GateOperator.GT, value=10))
    result = evaluate_gate(gate, 10)
    assert not result.passed


def test_evaluate_gt_false_less():
    """GT operator: failed when value is less than condition value."""
    from qa_framework.research.gate_evaluator import evaluate_gate
    gate = Gate(name="check", condition=GateCondition(operator=GateOperator.GT, value=10))
    result = evaluate_gate(gate, 5)
    assert not result.passed


def test_evaluate_gte_true():
    """GTE operator: passed when value is greater than or equal to condition value."""
    from qa_framework.research.gate_evaluator import evaluate_gate
    gate = Gate(name="check", condition=GateCondition(operator=GateOperator.GTE, value=10))
    result = evaluate_gate(gate, 10)
    assert result.passed


def test_evaluate_gte_true_greater():
    """GTE operator: passed when value is greater than condition value."""
    from qa_framework.research.gate_evaluator import evaluate_gate
    gate = Gate(name="check", condition=GateCondition(operator=GateOperator.GTE, value=10))
    result = evaluate_gate(gate, 15)
    assert result.passed


def test_evaluate_lt_true():
    """LT operator: passed when value is less than condition value."""
    from qa_framework.research.gate_evaluator import evaluate_gate
    gate = Gate(name="check", condition=GateCondition(operator=GateOperator.LT, value=10))
    result = evaluate_gate(gate, 5)
    assert result.passed


def test_evaluate_lt_false():
    """LT operator: failed when value is not less than condition value."""
    from qa_framework.research.gate_evaluator import evaluate_gate
    gate = Gate(name="check", condition=GateCondition(operator=GateOperator.LT, value=10))
    result = evaluate_gate(gate, 10)
    assert not result.passed


def test_evaluate_lte_true():
    """LTE operator: passed when value is less than or equal to condition value."""
    from qa_framework.research.gate_evaluator import evaluate_gate
    gate = Gate(name="check", condition=GateCondition(operator=GateOperator.LTE, value=10))
    result = evaluate_gate(gate, 10)
    assert result.passed


def test_evaluate_lte_false_less():
    """LTE operator: failed when value is greater than condition value."""
    from qa_framework.research.gate_evaluator import evaluate_gate
    gate = Gate(name="check", condition=GateCondition(operator=GateOperator.LTE, value=10))
    result = evaluate_gate(gate, 15)
    assert not result.passed


def test_gate_result_creation_from_evaluate():
    """Evaluate should return a GateResult."""
    from qa_framework.research.gate_evaluator import evaluate_gate
    gate = Gate(name="check", condition=GateCondition(operator=GateOperator.EQ, value=42))
    result = evaluate_gate(gate, 42)
    assert isinstance(result, GateResult)
    assert result.gate == "check"
    assert result.passed
    assert isinstance(result.evidence, str)