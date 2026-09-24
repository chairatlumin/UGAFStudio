"""Agent reliability tracking: outcomes, metrics, and scoring."""
from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path


class DispatchOutcome(str, Enum):
    SUCCESS = "success"
    FAILURE = "failure"
    TIMEOUT = "timeout"
    BLOCKED = "blocked"  # e.g., circuit breaker trip


@dataclass
class DispatchRecord:
    agent_id: str
    task_type: str
    model: str
    outcome: DispatchOutcome
    duration_ms: int
    confidence: float
    timestamp: float


@dataclass
class ReliabilityMetrics:
    agent_id: str
    total_dispatches: int
    repeatability: float  # success rate over last N runs
    failure_severity: float  # weighted severity score
    variance: float  # variance of confidence scores
    calibration: float | None  # P(success | confidence) alignment
    score: float  # composite 0.0-1.0


class ReliabilityTracker:
    """Track agent dispatch outcomes and compute reliability metrics."""

    def __init__(self, db_path: str = ".ai/a2a/reliability.db") -> None:
        if db_path != ":memory:":
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._create_tables()

    def _create_tables(self) -> None:
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS dispatch_outcomes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                agent_id TEXT NOT NULL,
                task_type TEXT NOT NULL,
                model TEXT NOT NULL,
                outcome TEXT NOT NULL,
                duration_ms INTEGER NOT NULL,
                confidence REAL NOT NULL,
                timestamp REAL NOT NULL DEFAULT (strftime('%s', 'now'))
            );
            CREATE INDEX IF NOT EXISTS idx_outcomes_agent ON dispatch_outcomes(agent_id);
            CREATE INDEX IF NOT EXISTS idx_outcomes_timestamp ON dispatch_outcomes(timestamp);
        """)
        self._conn.commit()

    def record_dispatch(
        self,
        agent_id: str,
        task_type: str,
        model: str,
        outcome: DispatchOutcome | str,
        duration_ms: int,
        confidence: float,
    ) -> int:
        if isinstance(outcome, str):
            outcome = DispatchOutcome(outcome)
        with self._conn:
            cur = self._conn.execute(
                """INSERT INTO dispatch_outcomes
                   (agent_id, task_type, model, outcome, duration_ms, confidence, timestamp)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (agent_id, task_type, model, outcome.value, duration_ms, confidence, time.time()),
            )
            lastrowid = cur.lastrowid
            if lastrowid is None:
                raise RuntimeError("Failed to insert dispatch outcome")
            return int(lastrowid)

    def get_reliability_score(self, agent_id: str) -> float:
        """Get composite reliability score 0.0-1.0 for an agent."""
        metrics = self.get_metrics(agent_id)
        return metrics.score

    def get_metrics(self, agent_id: str) -> ReliabilityMetrics:
        rows = self._conn.execute(
            """SELECT outcome, confidence, duration_ms FROM dispatch_outcomes
               WHERE agent_id = ? ORDER BY timestamp DESC LIMIT 100""",
            (agent_id,),
        ).fetchall()

        if not rows:
            return ReliabilityMetrics(
                agent_id=agent_id,
                total_dispatches=0,
                repeatability=0.5,
                failure_severity=0.0,
                variance=0.0,
                calibration=None,
                score=0.5,
            )

        total = len(rows)
        successes = sum(1 for r in rows if r["outcome"] == DispatchOutcome.SUCCESS.value)
        confidences = [r["confidence"] for r in rows]
        mean_conf = sum(confidences) / len(confidences)

        # Repeatability = success rate
        repeatability = successes / total

        # Failure severity = weighted average of failure outcomes
        failures = [r for r in rows if r["outcome"] != DispatchOutcome.SUCCESS.value]
        severity_map = {
            DispatchOutcome.FAILURE.value: 0.7,
            DispatchOutcome.TIMEOUT.value: 0.5,
            DispatchOutcome.BLOCKED.value: 0.3,
        }
        if failures:
            failure_severity = sum(
                severity_map.get(r["outcome"], 0.5) for r in failures
            ) / len(failures)
        else:
            failure_severity = 0.0

        # Variance of confidence scores
        if len(confidences) > 1:
            variance = sum((c - mean_conf) ** 2 for c in confidences) / (len(confidences) - 1)
        else:
            variance = 0.0

        # Calibration: correlation between confidence and success
        calibration: float | None = None
        if total >= 5:
            success_flags = [
                1.0 if r["outcome"] == DispatchOutcome.SUCCESS.value else 0.0
                for r in rows
            ]
            cal_mean = sum(success_flags) / len(success_flags)
            conf_mean = mean_conf
            numerator = sum(
                (success_flags[i] - cal_mean) * (confidences[i] - conf_mean)
                for i in range(len(rows))
            )
            denom_a = sum((s - cal_mean) ** 2 for s in success_flags) ** 0.5
            denom_b = sum((c - conf_mean) ** 2 for c in confidences) ** 0.5
            if denom_a > 0 and denom_b > 0:
                calibration = numerator / (denom_a * denom_b)

        # Composite score: weighted average
        score = (
            repeatability * 0.4
            + (1.0 - failure_severity) * 0.2
            + (1.0 - min(variance, 1.0)) * 0.2
            + (calibration if calibration is not None else 0.5) * 0.2
        )

        return ReliabilityMetrics(
            agent_id=agent_id,
            total_dispatches=total,
            repeatability=round(repeatability, 4),
            failure_severity=round(failure_severity, 4),
            variance=round(variance, 4),
            calibration=round(calibration, 4) if calibration is not None else None,
            score=round(max(0.0, min(1.0, score)), 4),
        )

    def get_agents(self) -> list[str]:
        """Get all tracked agent IDs."""
        rows = self._conn.execute(
            "SELECT DISTINCT agent_id FROM dispatch_outcomes"
        ).fetchall()
        return [r["agent_id"] for r in rows]

    def prune_old_records(self, max_age_days: int = 30) -> int:
        """Remove records older than N days."""
        cutoff = time.time() - (max_age_days * 86400)
        with self._conn:
            cur = self._conn.execute(
                "DELETE FROM dispatch_outcomes WHERE timestamp < ?", (cutoff,)
            )
            return cur.rowcount
