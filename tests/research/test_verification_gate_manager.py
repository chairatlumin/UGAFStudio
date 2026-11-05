from __future__ import annotations

from typing import List, Optional

from qa_framework.research.verification_gates import Gate, GateCondition, GateOperator, GateResult
from qa_framework.research.gate_evaluator import evaluate_gate
from qa_framework.research.recovery_protocol import select_recovery_action
from qa_framework.research.vgm_integration import record_gate_outcome, save_ledger, load_ledger
from qa_framework.research.ledger import ResearchLedger


def test_vgm_initialization():
    """VGM should initialize with a ledger and empty gate queue."""
    from qa_framework.research.verification_gate_manager import VerificationGateManager
    ledger = ResearchLedger()
    manager = VerificationGateManager(ledger=ledger)
    assert manager.ledger is ledger
    assert manager.gates == []


def test_vgm_add_gate():
    """VGM should add gates to the queue."""
    from qa_framework.research.verification_gate_manager import VerificationGateManager
    ledger = ResearchLedger()
    manager = VerificationGateManager(ledger=ledger)
    gate = Gate(name="check1", condition=GateCondition(operator=GateOperator.GT, value=10))
    manager.add_gate(gate)
    assert len(manager.gates) == 1
    assert manager.gates[0].name == "check1"


def test_vgm_run_all_passes():
    """VGM should pass when all gates pass."""
    from qa_framework.research.verification_gate_manager import VerificationGateManager
    ledger = ResearchLedger()
    manager = VerificationGateManager(ledger=ledger)
    gate1 = Gate(name="check1", condition=GateCondition(operator=GateOperator.GT, value=10))
    gate2 = Gate(name="check2", condition=GateCondition(operator=GateOperator.EQ, value=42))
    manager.add_gate(gate1)
    manager.add_gate(gate2)
    result = manager.run_all()
    assert result["overall_passed"]
    assert result["failed_gates"] == []


def test_vgm_run_all_one_fails():
    """VGM should stop on first failure and record the result."""
    from qa_framework.research.verification_gate_manager import VerificationGateManager
    ledger = ResearchLedger()
    manager = VerificationGateManager(ledger=ledger)
    gate1 = Gate(name="check1", condition=GateCondition(operator=GateOperator.GT, value=10))
    gate2 = Gate(name="check2", condition=GateCondition(operator=GateOperator.GT, value=100))
    manager.add_gate(gate1)
    manager.add_gate(gate2)
    result = manager.run_all()
    assert not result["overall_passed"]
    assert len(result["failed_gates"]) == 1


def test_vgm_run_all_with_recovery():
    """VGM should select recovery action when a gate fails."""
    from qa_framework.research.verification_gate_manager import VerificationGateManager
    ledger = ResearchLedger()
    manager = VerificationGateManager(ledger=ledger)
    gate1 = Gate(name="check1", condition=GateCondition(operator=GateOperator.GT, value=10))
    gate2 = Gate(name="check2", condition=GateCondition(operator=GateOperator.GT, value=100))
    manager.add_gate(gate1)
    manager.add_gate(gate2)
    result = manager.run_all()
    assert not result["overall_passed"]
    recovery = result["recovery_action"]
    assert recovery in ("retry", "redesign", "reset")


def test_vgm_run_all_gate_result_details():
    """VGM gate results should include gate name, passed status, and evidence."""
    from qa_framework.research.verification_gate_manager import VerificationGateManager
    ledger = ResearchLedger()
    manager = VerificationGateManager(ledger=ledger)
    gate = Gate(name="threshold_check", condition=GateCondition(operator=GateOperator.GT, value=10))
    manager.add_gate(gate)
    result = manager.run_all()
    assert "results" in result
    gate_result = result["results"][0]
    assert gate_result["gate"] == "threshold_check"
    assert "passed" in gate_result
    assert "evidence" in gate_result


def test_vgm_run_with_ledger_save():
    """VGM should save ledger after running gates."""
    from qa_framework.research.verification_gate_manager import VerificationGateManager
    import tempfile
    import os
    ledger = ResearchLedger()
    manager = VerificationGateManager(ledger=ledger)
    gate = Gate(name="check1", condition=GateCondition(operator=GateOperator.GT, value=10))
    manager.add_gate(gate)
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
        tmp_path = tmp.name
    try:
        result = manager.run_all()
        save_ledger(ledger, tmp_path)
        loaded = load_ledger(tmp_path)
        assert "check1" in loaded.gate_outcomes
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)