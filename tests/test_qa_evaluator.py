"""Tests for QAEvaluator."""

from __future__ import annotations

import pytest

from qa_framework.qa_evaluator import QAEvaluator, QAEvaluatorVerdict


class TestQAEvaluator:
    """Test QAEvaluator agent role."""

    def test_evaluator_approves_high_confidence(self) -> None:
        """High confidence results are approved regardless of outcome."""
        evaluator = QAEvaluator()
        verdict = evaluator.evaluate(
            agent_id="agent-1",
            task_id="t1",
            outcome="pass",
            confidence=0.95,
            evidence="All tests passed",
        )
        assert verdict.decision == QAEvaluatorVerdict.APPROVE
        assert verdict.confidence == pytest.approx(0.95)
        assert verdict.reason == "high_confidence"

    def test_evaluator_rejects_low_confidence(self) -> None:
        """Low confidence results are rejected for rework."""
        evaluator = QAEvaluator()
        verdict = evaluator.evaluate(
            agent_id="agent-1",
            task_id="t1",
            outcome="fail",
            confidence=0.3,
            evidence="unclear",
        )
        assert verdict.decision == QAEvaluatorVerdict.REJECT
        assert verdict.reason == "low_confidence"

    def test_evaluator_escalates_medium_confidence(self) -> None:
        """Medium confidence results are escalated for human review."""
        evaluator = QAEvaluator()
        verdict = evaluator.evaluate(
            agent_id="agent-1",
            task_id="t1",
            outcome="inconclusive",
            confidence=0.65,
        )
        assert verdict.decision == QAEvaluatorVerdict.ESCALATE
        assert verdict.reason == "medium_confidence_review_needed"

    def test_evaluate_batch(self) -> None:
        """Batch evaluation returns correct number of verdicts."""
        evaluator = QAEvaluator()
        results = [
            {"agent_id": "a1", "task_id": "t1", "outcome": "pass",
             "confidence": 0.9, "evidence": "ok"},
            {"agent_id": "a2", "task_id": "t2", "outcome": "fail",
             "confidence": 0.3, "evidence": "bad"},
        ]
        verdicts = evaluator.evaluate_batch(results)
        assert len(verdicts) == 2
        assert verdicts[0].decision == QAEvaluatorVerdict.APPROVE
        assert verdicts[1].decision == QAEvaluatorVerdict.REJECT


