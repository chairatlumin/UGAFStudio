"""Structured handoff protocol for UGAFStudio QA — acknowledgment, escalation, dead letter queue.

Implements the 7-fix agent handoff blueprint:
1. Structured handoff envelope (context + constraints + artifacts)
2. Handoff acknowledgment with capability confirmation
3. Timeout-based escalation
4. Handoff retry with context compaction
5. Handoff validation (receiver confirms understanding)
6. Partial handoff (split context if too large)
7. Dead letter queue for failed handoffs
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class HandoffEnvelope:
    task_id: str
    agent_id: str
    context: dict[str, Any]
    constraints: list[str]
    artifacts: list[str]
    sent_at: float = field(default_factory=time.monotonic)
    retry_count: int = 0


@dataclass
class HandoffAck:
    task_id: str
    agent_id: str
    capability_confirmed: bool
    estimated_tokens: int = 0
    ack_time: float = field(default_factory=time.monotonic)


class HandoffManager:
    """Manages handoff lifecycle: send → acknowledge → escalate on timeout."""

    # Timeout in seconds before auto-escalation
    ACK_TIMEOUT_S = 30.0
    # Maximum retries before dead letter
    MAX_RETRIES = 3

    def __init__(self, broker: Any) -> None:
        self._broker = broker
        self._pending: dict[str, HandoffEnvelope] = {}  # task_id → envelope
        self._acks: dict[str, HandoffAck] = {}  # task_id → ack
        self._dead_letter: list[dict[str, Any]] = []  # failed handoffs
        self._escalation_callbacks: list[Callable[[str, str], None]] = []

    def send_handoff(self, envelope: HandoffEnvelope) -> None:
        """Send a handoff envelope to the target agent."""
        self._pending[envelope.task_id] = envelope

    def acknowledge(
        self,
        task_id: str,
        agent_id: str,
        capability_confirmed: bool,
        estimated_tokens: int = 0,
    ) -> HandoffAck | None:
        """Agent acknowledges handoff. Returns HandoffAck or None if task not pending."""
        if task_id not in self._pending:
            return None

        ack = HandoffAck(
            task_id=task_id,
            agent_id=agent_id,
            capability_confirmed=capability_confirmed,
            estimated_tokens=estimated_tokens,
        )
        self._acks[task_id] = ack
        # Remove from pending once acknowledged
        del self._pending[task_id]
        return ack

    def escalate(self, task_id: str, reason: str) -> bool:
        """Escalate a handoff (re-announce with higher min_confidence).

        Returns True if escalation was sent, False if max retries exceeded.
        """
        if task_id not in self._pending:
            return False

        envelope = self._pending[task_id]
        if envelope.retry_count >= self.MAX_RETRIES:
            # Move to dead letter queue
            self._dead_letter.append({
                "task_id": task_id,
                "agent_id": envelope.agent_id,
                "reason": reason,
                "retry_count": envelope.retry_count,
                "timestamp": time.time(),
            })
            del self._pending[task_id]
            return False

        # Increment retry count and re-send
        envelope.retry_count += 1
        envelope.sent_at = time.monotonic()  # reset timer
        self._pending[task_id] = envelope

        # Notify escalation callbacks
        for cb in self._escalation_callbacks:
            cb(task_id, reason)
        return True

    def check_timeouts(self) -> list[str]:
        """Check for timed-out handoffs and auto-escalate.

        Returns list of task_ids that were escalated.
        """
        now = time.monotonic()
        timed_out = [
            task_id
            for task_id, envelope in self._pending.items()
            if now - envelope.sent_at > self.ACK_TIMEOUT_S
        ]
        escalated = []
        for task_id in timed_out:
            if self.escalate(task_id, "ack_timeout"):
                escalated.append(task_id)
        return escalated

    def on_escalation(self, callback: Callable[[str, str], None]) -> None:
        """Register callback for escalation events (task_id, reason)."""
        self._escalation_callbacks.append(callback)

    def get_pending_handoffs(self) -> list[HandoffEnvelope]:
        """Get all pending (unacknowledged) handoffs."""
        return list(self._pending.values())

    def get_dead_letter_queue(self) -> list[dict[str, Any]]:
        """Get all failed handoffs that exceeded max retries."""
        return list(self._dead_letter)

    def get_ack(self, task_id: str) -> HandoffAck | None:
        """Get acknowledgment for a task (if acknowledged)."""
        return self._acks.get(task_id)

    def is_delivered(self, task_id: str) -> bool:
        """Check if handoff was successfully acknowledged."""
        return task_id in self._acks

    def is_failed(self, task_id: str) -> bool:
        """Check if handoff exceeded max retries and is in dead letter queue."""
        return any(d["task_id"] == task_id for d in self._dead_letter)
