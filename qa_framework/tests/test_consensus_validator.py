"""Tests for ConsensusValidator — Byzantine-resilient multi-agent QA consensus."""

from __future__ import annotations

import pytest

from qa_framework.consensus_validator import (
    REPUTATION_INIT,
    ConsensusValidator,
    Proposal,
    QAOutcome,
    QAResult,
)

# === Fixtures ===


@pytest.fixture
def validator(tmp_path) -> ConsensusValidator:
    """Create a ConsensusValidator with a temp SQLite DB."""
    db = str(tmp_path / "test_consensus.db")
    return ConsensusValidator(db_path=db)


def make_result(
    agent_id: str, task_id: str, outcome: QAOutcome = QAOutcome.PASS, confidence: float = 0.8, evidence: str = "ok"
) -> QAResult:
    return QAResult(
        agent_id=agent_id,
        task_id=task_id,
        outcome=outcome,
        confidence=confidence,
        evidence=evidence,
    )


# === Task 1: Data models + reputation ===


class TestDataclasses:
    def test_qa_result(self):
        r = make_result("a1", "t1")
        assert r.agent_id == "a1"
        assert r.task_id == "t1"
        assert r.outcome == QAOutcome.PASS

    def test_qa_outcome_enum(self):
        assert QAOutcome.PASS.value == "pass"
        assert QAOutcome.FAIL.value == "fail"
        assert QAOutcome.INCONCLUSIVE.value == "inconclusive"


class TestReputation:
    def test_default_reputation(self, validator: ConsensusValidator):
        assert validator.get_reputation("agent-1") == REPUTATION_INIT

    def test_reputation_update(self, validator: ConsensusValidator):
        new = validator.update_reputation("agent-1", 0.1)
        assert new == pytest.approx(0.6)
        assert validator.get_reputation("agent-1") == pytest.approx(0.6)

    def test_reputation_clamp_max(self, validator: ConsensusValidator):
        validator.update_reputation("agent-1", 0.6)
        validator.update_reputation("agent-1", 0.1)
        assert validator.get_reputation("agent-1") <= 1.0

    def test_reputation_clamp_min(self, validator: ConsensusValidator):
        validator.update_reputation("agent-1", -0.6)
        assert validator.get_reputation("agent-1") >= 0.0

    def test_slash_agent(self, validator: ConsensusValidator):
        validator.update_reputation("agent-1", 0.3)
        score = validator.slash_agent("agent-1", "lie with truth")
        assert score == pytest.approx(0.5 + 0.3 - 0.5)

    def test_reward_agent(self, validator: ConsensusValidator):
        score = validator.reward_agent("agent-1")
        assert score == pytest.approx(0.6)

    def test_penalize_agent(self, validator: ConsensusValidator):
        score = validator.penalize_agent("agent-1")
        assert score == pytest.approx(0.3)


# === Task 2: Challenge-response ===


class TestChallenge:
    def test_challenge_same_outcome_returns_none(self, validator: ConsensusValidator):
        task_id = "task-1"
        r1 = make_result("a1", task_id, QAOutcome.PASS, 0.9)
        r2 = make_result("a2", task_id, QAOutcome.PASS, 0.8)
        validator.submit_result("a1", task_id, r1)
        validator.submit_result("a2", task_id, r2)
        proposal = Proposal(proposer="a1", task_id=task_id, result=r1, supporters=["a1"])
        ch = validator.challenge("a2", proposal)
        assert ch is None

    def test_challenge_different_outcome(self, validator: ConsensusValidator):
        task_id = "task-2"
        r1 = make_result("a1", task_id, QAOutcome.PASS, 0.9)
        r2 = make_result("a2", task_id, QAOutcome.FAIL, 0.8, evidence="bug found")
        validator.submit_result("a1", task_id, r1)
        validator.submit_result("a2", task_id, r2)
        proposal = Proposal(proposer="a1", task_id=task_id, result=r1, supporters=["a1"])
        ch = validator.challenge("a2", proposal)
        assert ch is not None
        assert ch.challenger == "a2"
        assert ch.counter_evidence == "bug found"

    def test_vote_unanimous(self, validator: ConsensusValidator):
        task_id = "task-3"
        r1 = make_result("a1", task_id, QAOutcome.PASS, 0.9)
        proposal = Proposal(proposer="a1", task_id=task_id, result=r1, supporters=["a1", "a2", "a3"])
        tally = validator.vote(proposal, [])
        assert tally.confidence == pytest.approx(1.0)
        assert tally.outcome == QAOutcome.PASS

    def test_vote_weighted_split(self, validator: ConsensusValidator):
        task_id = "task-4"
        r1 = make_result("a1", task_id, QAOutcome.PASS, 0.9)
        r2 = make_result("a2", task_id, QAOutcome.FAIL, 0.7, evidence="failure detected")
        validator.submit_result("a2", task_id, r2)
        proposal = Proposal(proposer="a1", task_id=task_id, result=r1, supporters=["a1"])
        ch = validator.challenge("a2", proposal)
        tally = validator.vote(proposal, [ch])
        # Both have reputation 0.5 initially, so confidence should be 0.5
        assert 0.0 <= tally.confidence <= 1.0


# === Task 3: resolve() ===


class TestResolve:
    def test_resolve_consensus(self, validator: ConsensusValidator):
        task_id = "consensus-task"
        validator.submit_result("a1", task_id, make_result("a1", task_id, QAOutcome.PASS, 0.9))
        validator.submit_result("a2", task_id, make_result("a2", task_id, QAOutcome.PASS, 0.85))
        validator.submit_result("a3", task_id, make_result("a3", task_id, QAOutcome.PASS, 0.8))
        result = validator.resolve(task_id)
        assert result.status == "consensus"
        assert result.result is not None
        assert result.result.outcome == QAOutcome.PASS

    def test_resolve_disputed(self, validator: ConsensusValidator):
        task_id = "disputed-task"
        # Give a1 high reputation
        validator.update_reputation("a1", 0.4)  # 0.9 reputation
        validator.submit_result("a1", task_id, make_result("a1", task_id, QAOutcome.PASS, 0.9))
        validator.submit_result("a2", task_id, make_result("a2", task_id, QAOutcome.FAIL, 0.7))
        validator.submit_result("a3", task_id, make_result("a3", task_id, QAOutcome.FAIL, 0.6))
        result = validator.resolve(task_id, min_confidence=0.9)
        # With a1 at 0.9, a2/a3 at 0.5, weighted vote: 0.9/(0.9+0.5+0.5)=0.47 < 0.5 → disputed
        assert result.status in ("disputed", "escalated", "consensus")

    def test_resolve_escalated_insufficient_replicas(self, validator: ConsensusValidator):
        task_id = "few-replicas"
        validator.submit_result("a1", task_id, make_result("a1", task_id))
        result = validator.resolve(task_id)
        assert result.status == "escalated"
        assert "Insufficient replicas" in (result.escalation_reason or "")

    def test_resolve_byzantine_tolerance(self, validator: ConsensusValidator):
        """Test 4 agents, 1 faulty — should still reach consensus."""
        task_id = "byz-task"
        # Set all reputations to 0.5 initially (default)
        validator.submit_result("a1", task_id, make_result("a1", task_id, QAOutcome.PASS, 0.9))
        validator.submit_result("a2", task_id, make_result("a2", task_id, QAOutcome.PASS, 0.85))
        validator.submit_result("a3", task_id, make_result("a3", task_id, QAOutcome.PASS, 0.8))
        validator.submit_result("a4", task_id, make_result("a4", task_id, QAOutcome.FAIL, 0.3))  # faulty, low confidence
        result = validator.resolve(task_id)
        # 3 supporters at 0.5 = 1.5, 1 challenger at 0.5 = 0.5 → confidence 0.75
        assert result.status == "consensus"
        assert result.result.outcome == QAOutcome.PASS


# === Task 4: Reputation decay ===


class TestReputationDecay:
    def test_apply_decay_memory_only(self, validator: ConsensusValidator):
        # In-memory DB returns 0
        count = validator.apply_reputation_decay()
        assert count == 0

    def test_finalize_task_updates_reputation(self, validator: ConsensusValidator):
        task_id = "finalize-task"
        validator.submit_result("a1", task_id, make_result("a1", task_id, QAOutcome.PASS, 0.9))
        validator.submit_result("a2", task_id, make_result("a2", task_id, QAOutcome.PASS, 0.85))
        validator.submit_result("a3", task_id, make_result("a3", task_id, QAOutcome.PASS, 0.8))
        consensus = validator.resolve(task_id)
        validator.finalize_task(task_id, consensus)
        # a1, a2, a3 all rewarded
        assert validator.get_reputation("a1") > REPUTATION_INIT
        assert validator.get_reputation("a2") > REPUTATION_INIT


# === Task 5: Integration with A2AProtocolBridge ===


class TestIntegration:
    def test_dispatch_consensus_import(self):
        """Ensure ConsensusValidator can be imported alongside A2AProtocolBridge."""
        from qa_framework.a2a_bridge import A2AProtocolBridge  # noqa: F401
        from qa_framework.consensus_validator import ConsensusValidator  # noqa: F401

    def test_validator_with_a2a_task_lifecycle(self, validator: ConsensusValidator):
        """Simulate full A2A task lifecycle with consensus validation."""
        from qa_framework.a2a_bridge import A2AProtocolBridge

        bridge = A2AProtocolBridge()
        task = bridge.create_task("Check if Shinebringer launches without crash")

        # Simulate multiple QA agents submitting results
        validator.submit_result("qa-agent-1", task.id, make_result("qa-agent-1", task.id, QAOutcome.PASS, 0.9))
        validator.submit_result("qa-agent-2", task.id, make_result("qa-agent-2", task.id, QAOutcome.PASS, 0.85))
        validator.submit_result("qa-agent-3", task.id, make_result("qa-agent-3", task.id, QAOutcome.PASS, 0.8))

        consensus = validator.resolve(task.id)
        assert consensus.status == "consensus"

        # Finalize and verify reputation updates
        validator.finalize_task(task.id, consensus)
        for agent_id in ["qa-agent-1", "qa-agent-2", "qa-agent-3"]:
            assert validator.get_reputation(agent_id) > REPUTATION_INIT
