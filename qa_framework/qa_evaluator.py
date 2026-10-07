"""QA Evaluator — validates QA results using evaluator-optimizer pattern."""

from __future__ import annotations

from typing import Any


class QAEvaluatorVerdict:
    """Verdict from QA evaluator on a single QA result."""

    APPROVE = "APPROVE"
    REJECT = "REJECT"
    ESCALATE = "ESCALATE"

    def __init__(self, decision: str, confidence: float, reason: str) -> None:
        self.decision = decision
        self.confidence = confidence
        self.reason = reason

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision": self.decision,
            "confidence": self.confidence,
            "reason": self.reason,
        }


class QAEvaluator:
    """Agent role for validating QA results (evaluator-optimizer pattern).

    Applies confidence-based rules to decide whether a QA result should be
    approved, rejected (sent back for rework), or escalated for human review.
    """

    def evaluate(
        self,
        agent_id: str,
        task_id: str,
        outcome: str,
        confidence: float,
        evidence: str = "",
    ) -> QAEvaluatorVerdict:
        """Evaluate a single QA result."""
        # High confidence → APPROVE
        if confidence >= 0.8:
            return QAEvaluatorVerdict(
                decision=QAEvaluatorVerdict.APPROVE,
                confidence=confidence,
                reason="high_confidence",
            )

        # Very low confidence → REJECT (send back for rework)
        if confidence < 0.5:
            return QAEvaluatorVerdict(
                decision=QAEvaluatorVerdict.REJECT,
                confidence=confidence,
                reason="low_confidence",
            )

        # Medium confidence → ESCALATE (needs human review)
        return QAEvaluatorVerdict(
            decision=QAEvaluatorVerdict.ESCALATE,
            confidence=confidence,
            reason="medium_confidence_review_needed",
        )

    def evaluate_batch(
        self, results: list[dict[str, Any]]
    ) -> list[QAEvaluatorVerdict]:
        """Evaluate a batch of QA results."""
        verdicts = []
        for result in results:
            verdict = self.evaluate(
                agent_id=result.get("agent_id", "unknown"),
                task_id=result.get("task_id", "unknown"),
                outcome=result.get("outcome", "unknown"),
                confidence=result.get("confidence", 0.0),
                evidence=result.get("evidence", ""),
            )
            verdicts.append(verdict)
        return verdicts
