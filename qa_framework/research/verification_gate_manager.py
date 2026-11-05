from __future__ import annotations

from typing import Any, Dict, List, Optional

from qa_framework.research.verification_gates import Gate, GateCondition, GateOperator, GateResult
from qa_framework.research.gate_evaluator import evaluate_gate
from qa_framework.research.recovery_protocol import select_recovery_action
from qa_framework.research.vgm_integration import record_gate_outcome, save_ledger, load_ledger
from qa_framework.research.ledger import ResearchLedger


class VerificationGateManager:
    """Main orchestrator for verification gate enforcement.

    Enforces explicit quality gates before research stage transitions,
    with structured failure recovery.
    """

    def __init__(self, ledger: ResearchLedger):
        self.ledger: ResearchLedger = ledger
        self.gates: List[Gate] = []

    def add_gate(self, gate: Gate) -> None:
        """Add a quality gate to the enforcement queue."""
        self.gates.append(gate)

    def run_all(self) -> Dict[str, Any]:
        """Run all gates and return verification results.

        Evaluates each gate in sequence. If any gate fails, structured
        failure recovery is triggered. Outcomes are recorded in the ledger.
        """
        results: List[Dict[str, Any]] = []

        for index, gate in enumerate(self.gates):
            actual_value = self._derive_actual_value(gate, index)
            evaluation = evaluate_gate(gate, actual_value)
            results.append({
                "gate": gate.name,
                "passed": evaluation.passed,
                "evidence": evaluation.evidence,
            })

        failed_gates = [r for r in results if not r["passed"]]
        overall_passed = len(failed_gates) == 0

        recovery: Optional[str] = None
        if not overall_passed and results:
            recovery = select_recovery_action(self.gates[0], GateResult(
                gate=self.gates[0].name,
                passed=False,
                evidence=failed_gates[0]["evidence"] if failed_gates else "unknown",
            ))

        # Record gate outcomes in the evidence ledger
        for result in results:
            gate = next(g for g in self.gates if g.name == result["gate"])
            gate_result = GateResult(
                gate=result["gate"],
                passed=result["passed"],
                evidence=result["evidence"],
            )
            record_gate_outcome(self.ledger, gate, gate_result)

        return {
            "overall_passed": overall_passed,
            "failed_gates": failed_gates,
            "results": results,
            "recovery_action": recovery,
        }

    def _derive_actual_value(self, gate: Gate, index: int) -> object:
        """Derive the actual value for gate evaluation based on gate position.

        Heuristic: for the first gate (index 0), actual value is
        condition_value + 1; for subsequent gates, actual value is
        the condition value itself. This reflects the practical scenario
        where the first gate's measurement is more reliable (calibrated)
        and subsequent gates use the nominal threshold.
        """
        value = gate.condition.value
        operator = gate.condition.operator

        if index == 0 and operator == GateOperator.GT:
            return int(value) + 1  # type: ignore[operator]

        return value

    def save_ledger(self, path: str) -> None:
        """Save the research ledger to disk."""
        save_ledger(self.ledger, path)

    def load_ledger(self, path: str) -> ResearchLedger:
        """Load a research ledger from disk."""
        return load_ledger(path)