"""Tests for HandoffManager — structured handoff protocol."""

from __future__ import annotations

import time

from qa_framework.handoff import HandoffEnvelope, HandoffManager


class FakeBroker:
    """Minimal fake CNPBroker for testing."""

    def __init__(self) -> None:
        self.handoffs: list[tuple[str, str, bool]] = []

    def record_handoff(self, task_id: str, agent_id: str, success: bool) -> None:
        self.handoffs.append((task_id, agent_id, success))

    def get_reputation(self, agent_id: str) -> float:
        return 0.5


class TestHandoffManager:
    def setup_method(self) -> None:
        self.broker = FakeBroker()
        self.mgr = HandoffManager(self.broker)

    def test_handoff_acknowledges_and_escalates(self) -> None:
        envelope = HandoffEnvelope(
            task_id="task-1",
            agent_id="unreal-specialist",
            context={"file": "qa_framework/a2a_bridge.py"},
            constraints=["no_external_deps"],
            artifacts=["lesson: ue5-crash-fix"],
        )
        self.mgr.send_handoff(envelope)
        ack = self.mgr.acknowledge("task-1", "unreal-specialist", capability_confirmed=True)
        assert ack is not None
        assert ack.capability_confirmed

    def test_handoff_not_pending_returns_none(self) -> None:
        ack = self.mgr.acknowledge("nonexistent", "agent", capability_confirmed=True)
        assert ack is None

    def test_handoff_escalation_increments_retry(self) -> None:
        envelope = HandoffEnvelope(
            task_id="task-1",
            agent_id="agent-a",
            context={},
            constraints=[],
            artifacts=[],
        )
        self.mgr.send_handoff(envelope)
        result = self.mgr.escalate("task-1", "test_reason")
        assert result is True
        pending = self.mgr.get_pending_handoffs()
        assert len(pending) == 1
        assert pending[0].retry_count == 1

    def test_handoff_max_retries_moves_to_dead_letter(self) -> None:
        envelope = HandoffEnvelope(
            task_id="task-1",
            agent_id="agent-a",
            context={},
            constraints=[],
            artifacts=[],
        )
        self.mgr.send_handoff(envelope)
        # Escalate MAX_RETRIES times
        for _ in range(HandoffManager.MAX_RETRIES):
            self.mgr.escalate("task-1", "test_reason")
        # Next escalate should fail (too many retries)
        result = self.mgr.escalate("task-1", "one_too_many")
        assert result is False
        # Should be in dead letter queue
        dlq = self.mgr.get_dead_letter_queue()
        assert len(dlq) == 1
        assert dlq[0]["task_id"] == "task-1"
        assert dlq[0]["retry_count"] == HandoffManager.MAX_RETRIES

    def test_handoff_timeout_triggers_escalation(self) -> None:
        envelope = HandoffEnvelope(
            task_id="task-1",
            agent_id="agent-a",
            context={},
            constraints=[],
            artifacts=[],
        )
        # Set sent_at to past to force timeout
        envelope.sent_at = time.monotonic() - HandoffManager.ACK_TIMEOUT_S - 1.0
        self.mgr.send_handoff(envelope)
        escalated = self.mgr.check_timeouts()
        assert len(escalated) == 1
        assert escalated[0] == "task-1"

    def test_handoff_is_delivered_after_ack(self) -> None:
        envelope = HandoffEnvelope(
            task_id="task-1",
            agent_id="agent-a",
            context={},
            constraints=[],
            artifacts=[],
        )
        self.mgr.send_handoff(envelope)
        assert not self.mgr.is_delivered("task-1")
        self.mgr.acknowledge("task-1", "agent-a", capability_confirmed=True)
        assert self.mgr.is_delivered("task-1")

    def test_handoff_is_failed_after_max_retries(self) -> None:
        envelope = HandoffEnvelope(
            task_id="task-1",
            agent_id="agent-a",
            context={},
            constraints=[],
            artifacts=[],
        )
        self.mgr.send_handoff(envelope)
        for _ in range(HandoffManager.MAX_RETRIES + 1):
            self.mgr.escalate("task-1", "reason")
        assert self.mgr.is_failed("task-1")

    def test_escalation_callback_fires(self) -> None:
        callback_fired: list[tuple[str, str]] = []
        self.mgr.on_escalation(lambda task_id, reason: callback_fired.append((task_id, reason)))
        envelope = HandoffEnvelope(
            task_id="task-1",
            agent_id="agent-a",
            context={},
            constraints=[],
            artifacts=[],
        )
        self.mgr.send_handoff(envelope)
        self.mgr.escalate("task-1", "test_reason")
        assert len(callback_fired) == 1
        assert callback_fired[0] == ("task-1", "test_reason")
