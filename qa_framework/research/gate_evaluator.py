from __future__ import annotations

from typing import Any

from qa_framework.research.verification_gates import Gate, GateCondition, GateOperator, GateResult


def evaluate_gate(gate: Gate, actual_value: Any) -> GateResult:
    """Evaluate a gate against an actual value and return a GateResult."""
    condition = gate.condition
    operator = condition.operator
    value = condition.value

    if operator == GateOperator.EQ:
        passed = actual_value == value
    elif operator == GateOperator.NE:
        passed = actual_value != value
    elif operator == GateOperator.GT:
        passed = actual_value > value
    elif operator == GateOperator.GTE:
        passed = actual_value >= value
    elif operator == GateOperator.LT:
        passed = actual_value < value
    elif operator == GateOperator.LTE:
        passed = actual_value <= value
    else:
        raise ValueError(f"Unsupported gate operator: {operator}")

    evidence = f"gate={gate.name} operator={operator.name} actual={actual_value} expected={value}"
    return GateResult(
        gate=gate.name,
        passed=passed,
        evidence=evidence,
    )