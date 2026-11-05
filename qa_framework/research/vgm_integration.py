from __future__ import annotations

import json
from dataclasses import asdict
from typing import Optional

from qa_framework.research.verification_gates import Gate, GateCondition, GateOperator, GateResult
from qa_framework.research.ledger import ResearchLedger, GateResult as LedgerGateResult
from qa_framework.research.recovery_protocol import select_recovery_action


def record_gate_outcome(ledger: ResearchLedger, gate: Gate, result: GateResult) -> None:
    """Record a gate outcome to the research ledger."""
    ledger.record_gate_outcome(LedgerGateResult(
        gate=gate.name,
        passed=result.passed,
        evidence=result.evidence,
        timestamp=result.timestamp or None,
    ))


def select_recovery_for_gate(gate: Gate, result: GateResult) -> str:
    """Select a recovery action for a failed gate."""
    return select_recovery_action(gate, result)


def save_ledger(ledger: ResearchLedger, path: str) -> None:
    """Save the ledger to a JSON file at the specified path."""
    data = {
        "gate_outcomes": {k: asdict(v) for k, v in ledger.gate_outcomes.items()},
    }
    with open(path, 'w') as f:
        json.dump(data, f, indent=2)


def load_ledger(path: str) -> ResearchLedger:
    """Load a ledger from a JSON file at the specified path."""
    try:
        with open(path, 'r') as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return ResearchLedger(path)
    ledger = ResearchLedger(path)
    ledger.gate_outcomes = {k: LedgerGateResult(**v) for k, v in data.get("gate_outcomes", {}).items()}
    return ledger