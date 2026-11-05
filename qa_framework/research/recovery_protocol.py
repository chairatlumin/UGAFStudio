from __future__ import annotations

from typing import Optional

from qa_framework.research.verification_gates import Gate, GateCondition, GateOperator, GateResult


def select_recovery_action(gate: Gate, result: GateResult) -> str:
    """Select a recovery action based on the gate and result of a failed gate check.

    Heuristics:
    - 'reset' if the evidence indicates critical state corruption
    - 'redesign' if the evidence contains 'complex' or the gate operator is NE
    - 'retry' as the default for transient / soft failures
    """
    evidence = result.evidence.lower()

    if "critical" in evidence or "corrupted" in evidence:
        return "reset"
    if "complex" in evidence or gate.condition.operator == GateOperator.NE:
        return "redesign"
    return "retry"