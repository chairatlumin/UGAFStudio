from __future__ import annotations

from typing import Optional

from qa_framework.research.verification_gates import Gate, GateCondition, GateOperator, GateResult
from qa_framework.research.ledger import ResearchLedger, GateResult as LedgerGateResult
from qa_framework.research.recovery_protocol import select_recovery_action


def test_integration_record_gate_outcome():
    """VGM integration should record a gate outcome to the ledger."""
    from qa_framework.research.vgm_integration import record_gate_outcome
    ledger = ResearchLedger()
    gate = Gate(name="threshold_check", condition=GateCondition(operator=GateOperator.GT, value=10))
    result = GateResult(gate="threshold_check", passed=False, evidence="value 5 not > 10")
    record_gate_outcome(ledger, gate, result)
    assert "threshold_check" in ledger.gate_outcomes


def test_integration_recovery_action():
    """VGM integration should select recovery action for failed gates."""
    from qa_framework.research.vgm_integration import select_recovery_for_gate
    gate = Gate(name="threshold_check", condition=GateCondition(operator=GateOperator.GT, value=10))
    result = GateResult(gate="threshold_check", passed=False, evidence="value 5 not > 10")
    action = select_recovery_for_gate(gate, result)
    assert action == "retry"


def test_integration_ledger_save_load():
    """VGM integration should support ledger save and load."""
    from qa_framework.research.vgm_integration import save_ledger, load_ledger
    ledger = ResearchLedger()
    save_ledger(ledger, "/tmp/test_ledger.json")
    loaded = load_ledger("/tmp/test_ledger.json")
    assert isinstance(loaded, ResearchLedger)