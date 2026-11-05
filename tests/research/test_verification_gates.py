from __future__ import annotations

from enum import Enum
from typing import Optional

from qa_framework.research.verification_gates import GateOperator, GateCondition, Gate, GateResult


def test_gate_operator_enum():
    assert GateOperator.EQ.value == "=="
    assert GateOperator.NE.value == "!="
    assert GateOperator.GT.value == ">"
    assert GateOperator.GTE.value == ">="
    assert GateOperator.LT.value == "<"
    assert GateOperator.LTE.value == "<="


def test_gate_condition_creation():
    condition = GateCondition(operator=GateOperator.EQ, value=42)
    assert condition.operator == GateOperator.EQ
    assert condition.value == 42


def test_gate_creation():
    gate = Gate(name="threshold_check", condition=GateCondition(operator=GateOperator.GT, value=10))
    assert gate.name == "threshold_check"
    assert gate.condition.operator == GateOperator.GT
    assert gate.condition.value == 10


def test_gate_result_creation():
    result = GateResult(gate="threshold_check", passed=True, evidence="value 15 > 10")
    assert result.gate == "threshold_check"
    assert result.passed
    assert result.evidence == "value 15 > 10"


def test_gate_result_creation_failed():
    result = GateResult(gate="threshold_check", passed=False, evidence="value 5 not > 10")
    assert not result.passed
    assert result.evidence == "value 5 not > 10"