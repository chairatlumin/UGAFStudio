"""Consensus validation for multi-agent QA — Byzantine-resilient voting with reputation."""

from __future__ import annotations

import sqlite3
import statistics
from enum import Enum
from typing import NamedTuple, Optional


class QAOutcome(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    INCONCLUSIVE = "inconclusive"


class QAResult(NamedTuple):
    agent_id: str
    task_id: str
    outcome: QAOutcome
    confidence: float  # 0.0-1.0
    evidence: str  # agent's reasoning/evidence


class Proposal(NamedTuple):
    proposer: str
    task_id: str
    result: QAResult
    supporters: list[str]


class Challenge(NamedTuple):
    challenger: str
    proposal: Proposal
    counter_evidence: str
    confidence: float


class VoteTally(NamedTuple):
    supporters: list[str]
    challengers: list[str]
    confidence: float  # 0.0-1.0
    outcome: QAOutcome | str


class ConsensusResult(NamedTuple):
    status: str  # "consensus" | "disputed" | "escalated"
    result: Optional[QAResult]
    confidence: float
    votes: list[VoteTally]
    escalation_reason: Optional[str]


# Reputation constants
REPUTATION_INIT = 0.5
REPUTATION_DELTA_CORRECT = 0.1
REPUTATION_DELTA_INCORRECT = -0.2
REPUTATION_DELTA_LIE_WITH_TRUTH = -0.5
REPUTATION_MIN = 0.0
REPUTATION_MAX = 1.0
REPUTATION_DECAY_RATE = 0.01  # per 30 days
REPUTATION_DECAY_INTERVAL_DAYS = 30


class ConsensusValidator:
    """Byzantine-resilient consensus for multi-agent QA results.

    Uses weighted voting with reputation tracking. Designed to tolerate
    up to f < N/3 Byzantine (arbitrarily faulty) agents.
    """

    REPUTATION_SCHEMA = """
    CREATE TABLE IF NOT EXISTS agent_reputation (
        agent_id TEXT PRIMARY KEY,
        score REAL NOT NULL DEFAULT 0.5,
        total_votes INTEGER NOT NULL DEFAULT 0,
        correct_votes INTEGER NOT NULL DEFAULT 0,
        last_active TEXT NOT NULL DEFAULT (datetime('now'))
    );
    """

    def __init__(self, db_path: str = ":memory:", min_replicas: int = 3, consensus_mode: str = "weighted") -> None:
        """Initialize consensus validator.

        Args:
            db_path: SQLite path for reputation storage
            min_replicas: minimum number of agent results required
            consensus_mode: "weighted" (naive voting) or "pbft" (3-phase commit)
        """
        self.db_path = db_path
        self.min_replicas = min_replicas
        self.consensus_mode = consensus_mode
        self._results: dict[str, list[QAResult]] = {}
        if db_path != ":memory:":
            self._initialize_reputation_table()

    def _initialize_reputation_table(self) -> None:
        """Create reputation table if not exists."""
        conn = sqlite3.connect(self.db_path)
        try:
            conn.executescript(self.REPUTATION_SCHEMA)
            conn.commit()
        finally:
            conn.close()

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.executescript(self.REPUTATION_SCHEMA)
        return conn

    def submit_result(self, agent_id: str, task_id: str, result: QAResult) -> None:
        """Submit a QA result from an agent."""
        if task_id not in self._results:
            self._results[task_id] = []
        self._results[task_id].append(result)

    def resolve(self, task_id: str, min_confidence: float = 0.7) -> ConsensusResult:
        """Resolve consensus for a task. Main entry point."""
        results = self._get_results_for_task(task_id)

        if len(results) < self.min_replicas:
            return ConsensusResult(
                status="escalated",
                result=None,
                confidence=0.0,
                votes=[],
                escalation_reason=f"Insufficient replicas: {len(results)} < {self.min_replicas}",
            )

        if self.consensus_mode == "pbft":
            return self._resolve_pbft(task_id, results, min_confidence)

        # Weighted voting mode (original)
        outcome_counts: dict[str, int] = {}
        for r in results:
            outcome_counts[r.outcome.value] = outcome_counts.get(r.outcome.value, 0) + 1

        # Pick the outcome with most votes as primary
        primary_outcome = max(outcome_counts, key=outcome_counts.get)  # type: ignore
        primary_results = [r for r in results if r.outcome.value == primary_outcome]
        minority_results = [r for r in results if r.outcome.value != primary_outcome]

        if not minority_results:
            # Unanimous agreement
            avg_confidence = statistics.mean(r.confidence for r in primary_results)
            return ConsensusResult(
                status="consensus",
                result=primary_results[0],
                confidence=avg_confidence,
                votes=[],
                escalation_reason=None,
            )

        # Create proposal from primary outcome
        primary = max(primary_results, key=lambda r: r.confidence)
        proposal = Proposal(
            proposer=primary.agent_id,
            task_id=task_id,
            result=primary,
            supporters=[r.agent_id for r in primary_results],
        )

        # Generate challenges from minority
        challenges = []
        for r in minority_results:
            ch = self.challenge(r.agent_id, proposal)
            if ch is not None:
                challenges.append(ch)

        tally = self.vote(proposal, challenges)

        if tally.confidence >= min_confidence:
            status = "consensus"
            escalation_reason = None
        elif tally.confidence > 0.5:
            status = "disputed"
            escalation_reason = None
        else:
            status = "escalated"
            escalation_reason = (
                f"Consensus confidence {tally.confidence:.2f} below "
                f"minimum {min_confidence:.2f}"
            )

        return ConsensusResult(
            status=status,
            result=primary if status != "escalated" else None,
            confidence=tally.confidence,
            votes=[tally],
            escalation_reason=escalation_reason,
        )

    def challenge(self, agent_id: str, proposal: Proposal) -> Optional[Challenge]:
        """Generate challenge if agent's result differs from proposal."""
        results = self._get_results_for_task(proposal.task_id)
        agent_result = next((r for r in results if r.agent_id == agent_id), None)

        if agent_result is None:
            return None

        # Challenge if outcomes differ
        if agent_result.outcome != proposal.result.outcome:
            return Challenge(
                challenger=agent_id,
                proposal=proposal,
                counter_evidence=agent_result.evidence,
                confidence=agent_result.confidence,
            )
        return None

    def vote(self, proposal: Proposal, challenges: list[Challenge]) -> VoteTally:
        """Weighted vote by agent reputation."""
        supporter_weight = sum(self.get_reputation(a) for a in proposal.supporters)
        challenger_weight = sum(self.get_reputation(c.challenger) for c in challenges)

        total = supporter_weight + challenger_weight
        if total == 0:
            confidence = 0.5  # No reputation data → uncertain
        else:
            confidence = supporter_weight / total

        # Determine outcome
        if confidence > 0.5:
            outcome = proposal.result.outcome
        elif confidence < 0.5 and challenges:
            # Flip to first challenger's outcome
            outcome = QAOutcome.INCONCLUSIVE
            # Get challenger outcome from results
            ch = challenges[0]
            results = self._get_results_for_task(proposal.task_id)
            cr = next((r for r in results if r.agent_id == ch.challenger), None)
            if cr:
                outcome = cr.outcome
        else:
            outcome = "disputed"  # type: ignore

        return VoteTally(
            supporters=proposal.supporters,
            challengers=[c.challenger for c in challenges],
            confidence=confidence,
            outcome=outcome,
        )

    def get_reputation(self, agent_id: str) -> float:
        """Get agent's reputation score 0.0-1.0."""
        if self.db_path == ":memory:":
            return REPUTATION_INIT
        conn = self._get_conn()
        try:
            row = conn.execute(
                "SELECT score FROM agent_reputation WHERE agent_id = ?", (agent_id,)
            ).fetchone()
            return row["score"] if row else REPUTATION_INIT
        finally:
            conn.close()

    def update_reputation(
        self, agent_id: str, delta: float, reason: str = ""
    ) -> float:
        """Update reputation with atomic transaction. Returns new score."""
        new_score = max(REPUTATION_MIN, min(REPUTATION_MAX, self.get_reputation(agent_id) + delta))
        conn = self._get_conn()
        try:
            with conn:
                conn.execute(
                    """
                    INSERT INTO agent_reputation (agent_id, score, total_votes, correct_votes, last_active)
                    VALUES (?, ?, 1, ?, datetime('now'))
                    ON CONFLICT(agent_id) DO UPDATE SET
                        score = excluded.score,
                        total_votes = agent_reputation.total_votes + 1,
                        correct_votes = agent_reputation.correct_votes + ?,
                        last_active = datetime('now')
                    """,
                    (
                        agent_id,
                        new_score,
                        1 if delta > 0 else 0,
                        1 if delta > 0 else 0,
                    ),
                )
        finally:
            conn.close()
        return new_score

    def slash_agent(self, agent_id: str, reason: str) -> float:
        """Harsh penalty for lie-with-truth (-0.5). Returns new score."""
        return self.update_reputation(agent_id, REPUTATION_DELTA_LIE_WITH_TRUTH, reason)

    def reward_agent(self, agent_id: str, reason: str = "") -> float:
        """Reward correct prediction (+0.1). Returns new score."""
        return self.update_reputation(agent_id, REPUTATION_DELTA_CORRECT, reason)

    def penalize_agent(self, agent_id: str, reason: str = "") -> float:
        """Penalize incorrect prediction (-0.2). Returns new score."""
        return self.update_reputation(agent_id, REPUTATION_DELTA_INCORRECT, reason)

    def apply_reputation_decay(self) -> int:
        """Decay reputations toward 0.5 for inactive agents. Returns count affected."""
        if self.db_path == ":memory:":
            return 0
        conn = self._get_conn()
        try:
            cutoff_days = REPUTATION_DECAY_INTERVAL_DAYS
            with conn:
                cur = conn.execute(
                    """
                    UPDATE agent_reputation
                    SET score = CASE
                        WHEN score > 0.5 THEN MAX(0.5, score - ?)
                        WHEN score < 0.5 THEN MIN(0.5, score + ?)
                        ELSE score
                    END
                    WHERE last_active < datetime('now', ?)
                    """,
                    (REPUTATION_DECAY_RATE, REPUTATION_DECAY_RATE, f"-{cutoff_days} days"),
                )
                return cur.rowcount
        finally:
            conn.close()

    def _get_results_for_task(self, task_id: str) -> list[QAResult]:
        """Retrieve all results for a task."""
        return self._results.get(task_id, [])

    def _resolve_pbft(
        self, task_id: str, results: list[QAResult], min_confidence: float
    ) -> ConsensusResult:
        """Resolve consensus using PBFT 3-phase commit."""
        from qa_framework.pbft_consensus import PBFTNetwork

        # Determine unique outcomes
        outcome_counts: dict[str, int] = {}
        for r in results:
            outcome_counts[r.outcome.value] = outcome_counts.get(r.outcome.value, 0) + 1

        # Pick majority outcome as proposal value
        proposed_value = max(outcome_counts, key=outcome_counts.get)  # type: ignore

        # Calculate f (max faulty nodes) — tolerate up to n//3
        n = len(results)
        f = max(1, n // 3)

        # Build PBFT network
        network = PBFTNetwork(view=0, f=f)
        for r in results:
            import os
            node = network.create_node(r.agent_id, private_key=os.urandom(32))

        # Run consensus
        pbft_result = network.propose(task_id, proposed_value)

        if pbft_result.committed:
            # Find matching QAResult for committed value
            matching = [r for r in results if r.outcome.value == pbft_result.value]
            best = max(matching, key=lambda r: r.confidence)
            avg_confidence = sum(r.confidence for r in matching) / len(matching)
            return ConsensusResult(
                status="consensus" if avg_confidence >= min_confidence else "disputed",
                result=best,
                confidence=avg_confidence,
                votes=[],
                escalation_reason=None,
            )
        else:
            return ConsensusResult(
                status="escalated",
                result=None,
                confidence=0.0,
                votes=[],
                escalation_reason="PBFT could not reach quorum",
            )

    def finalize_task(self, task_id: str, consensus: ConsensusResult) -> None:
        """Update reputations based on consensus outcome and clean up results."""
        if consensus.status == "escalated":
            # No reputation update on escalation
            return

        results = self._get_results_for_task(task_id)
        winning_outcome = consensus.result.outcome if consensus.result else None

        for r in results:
            if winning_outcome is not None and r.outcome == winning_outcome:
                self.reward_agent(r.agent_id, f"Task {task_id}: correct")
            else:
                self.penalize_agent(r.agent_id, f"Task {task_id}: incorrect")

        # Clean up
        self._results.pop(task_id, None)
