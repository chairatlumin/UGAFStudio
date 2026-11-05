"""Tests for A2AProtocolBridge CNP integration."""

from __future__ import annotations

from qa_framework.a2a_bridge import A2AProtocolBridge
from qa_framework.cnp_broker import BidEnvelope


class TestBridgeCNP:
    def setup_method(self) -> None:
        self.bridge = A2AProtocolBridge(lesson_db_path=":memory:")

    def test_bridge_uses_cnp_for_dispatch(self) -> None:
        task = self.bridge.create_task("Fix UE5 crash", context_id=None)
        self.bridge.announce_task_for_bid(task.id, "Fix UE5 crash", tags=["ue5", "crash"])
        bid = BidEnvelope(
            agent_id="unreal-specialist",
            task_id=task.id,
            confidence=0.95,
            estimated_cost_usd=0.02,
            capability_match=0.9,
        )
        self.bridge.submit_bid(bid)
        winner = self.bridge.award_and_dispatch(task.id)
        assert winner is not None
        assert winner.agent_id == "unreal-specialist"

    def test_bridge_cnp_no_bids_returns_none(self) -> None:
        task = self.bridge.create_task("Fix crash", context_id=None)
        self.bridge.announce_task_for_bid(task.id, "Fix crash", tags=["ue5"])
        winner = self.bridge.award_and_dispatch(task.id)
        assert winner is None

    def test_bridge_escalate_failed_handoff(self) -> None:
        result = self.bridge.escalate_failed_handoff("task-does-not-exist", "test")
        # Task doesn't exist in pending, so escalation returns False
        assert result is False

    def test_bridge_get_agent_reputation(self) -> None:
        # Unknown agent should return neutral prior
        rep = self.bridge.get_agent_reputation("unknown-agent")
        assert rep == 0.5
