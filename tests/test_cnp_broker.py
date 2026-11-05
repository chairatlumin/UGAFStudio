"""Tests for CNPBroker — Contract Net Protocol bidding layer."""

from __future__ import annotations

from qa_framework.cnp_broker import BidEnvelope, CNPBroker


class TestCNPBroker:
    def setup_method(self) -> None:
        self.broker = CNPBroker(":memory:")

    def teardown_method(self) -> None:
        self.broker.close()

    def test_cnp_broker_records_bid_and_awards(self) -> None:
        self.broker.announce_task("task-1", "Fix UE5 D3D12 crash", tags=["ue5", "crash"])
        bid = BidEnvelope(
            agent_id="unreal-specialist",
            task_id="task-1",
            confidence=0.95,
            estimated_cost_usd=0.02,
            capability_match=0.9,
        )
        self.broker.submit_bid(bid)
        winner = self.broker.award_task("task-1")
        assert winner is not None
        assert winner.agent_id == "unreal-specialist"

    def test_cnp_broker_highest_score_wins(self) -> None:
        self.broker.announce_task("task-1", "Fix UE5 crash", tags=["ue5"])
        # Low bid
        self.broker.submit_bid(BidEnvelope(
            agent_id="generalist", task_id="task-1",
            confidence=0.5, estimated_cost_usd=0.10, capability_match=0.3,
        ))
        # High bid
        self.broker.submit_bid(BidEnvelope(
            agent_id="specialist", task_id="task-1",
            confidence=0.95, estimated_cost_usd=0.02, capability_match=0.9,
        ))
        winner = self.broker.award_task("task-1")
        assert winner is not None
        assert winner.agent_id == "specialist"

    def test_cnp_broker_filters_low_confidence(self) -> None:
        self.broker.announce_task("task-1", "Fix crash", tags=["ue5"], min_confidence=0.7)
        # Too low confidence
        self.broker.submit_bid(BidEnvelope(
            agent_id="low-conf", task_id="task-1",
            confidence=0.3, estimated_cost_usd=0.01, capability_match=0.9,
        ))
        winner = self.broker.award_task("task-1")
        assert winner is None  # no valid bids

    def test_cnp_broker_empty_bids_returns_none(self) -> None:
        self.broker.announce_task("task-1", "Fix crash", tags=["ue5"])
        winner = self.broker.award_task("task-1")
        assert winner is None

    def test_cnp_broker_reputation_tracks_success(self) -> None:
        # Record some handoffs
        self.broker.record_handoff("task-1", "agent-a", success=True)
        self.broker.record_handoff("task-2", "agent-a", success=True)
        self.broker.record_handoff("task-3", "agent-a", success=False)
        self.broker.record_handoff("task-4", "agent-b", success=True)

        # agent-a: 2/3 success
        rep_a = self.broker.get_reputation("agent-a")
        assert abs(rep_a - 2 / 3) < 0.01

        # agent-b: 1/1 success
        rep_b = self.broker.get_reputation("agent-b")
        assert rep_b == 1.0

    def test_cnp_broker_unknown_agent_reputation_is_neutral(self) -> None:
        rep = self.broker.get_reputation("unknown-agent")
        assert rep == 0.5

    def test_cnp_broker_cost_efficiency_bonus(self) -> None:
        """Cheaper tasks should score higher when both are above cost=1.0 threshold."""
        self.broker.announce_task("task-1", "Fix crash", tags=["ue5"])
        # Expensive (cost > 1.0 gets capped at 1.0 efficiency)
        self.broker.submit_bid(BidEnvelope(
            agent_id="expensive", task_id="task-1",
            confidence=0.8, estimated_cost_usd=5.0, capability_match=0.8,
        ))
        # Moderately priced (cost < 1.0 gets raw efficiency > 1.0)
        self.broker.submit_bid(BidEnvelope(
            agent_id="moderate", task_id="task-1",
            confidence=0.8, estimated_cost_usd=0.5, capability_match=0.8,
        ))
        winner = self.broker.award_task("task-1")
        assert winner is not None
        # moderate wins: cost_eff = 1.0/0.5 = 2.0 vs expensive: 1.0/5.0 = 0.2
        assert winner.agent_id == "moderate"
