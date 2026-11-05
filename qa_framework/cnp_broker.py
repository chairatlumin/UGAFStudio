"""Contract Net Protocol (CNP) bidding layer for UGAFStudio QA.

Implements capability-based task allocation with reputation scoring:
- announce_task: broadcast task to eligible agents
- submit_bid: agents bid with confidence + estimated cost
- award_task: highest-score bid wins (score = confidence*0.4 + match*0.4 + cost_efficiency*0.2)
- record_handoff: track success/failure for reputation
- get_reputation: agent success rate (0.0-1.0)
"""

from __future__ import annotations

import sqlite3
import threading
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class BidEnvelope:
    agent_id: str
    task_id: str
    confidence: float  # 0.0-1.0
    estimated_cost_usd: float
    capability_match: float  # 0.0-1.0, how well agent matches task tags
    bid_time: str = field(default_factory=lambda: datetime.now().isoformat())


class CNPBroker:
    """SQLite-backed Contract Net Protocol broker for multi-agent task allocation.

    Thread-safe via WAL mode and per-thread connections.
    """

    def __init__(self, db_path: str = ".ai/a2a/cnp.db") -> None:
        self.db_path = db_path
        self._local = threading.local()
        self._init_db()

    def get_conn(self) -> sqlite3.Connection:
        if not hasattr(self._local, "conn") or self._local.conn is None:
            conn = sqlite3.connect(self.db_path, timeout=30)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=5000")
            conn.row_factory = sqlite3.Row
            self._local.conn = conn
        return self._local.conn  # type: ignore[no-any-return]

    def close(self) -> None:
        if hasattr(self._local, "conn") and self._local.conn is not None:
            self._local.conn.close()
            self._local.conn = None

    def _init_db(self) -> None:
        conn = self.get_conn()
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS cnp_tasks (
                task_id TEXT PRIMARY KEY,
                description TEXT NOT NULL,
                tags TEXT NOT NULL DEFAULT '[]',
                min_confidence REAL DEFAULT 0.5,
                status TEXT DEFAULT 'open',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS cnp_bids (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id TEXT NOT NULL,
                agent_id TEXT NOT NULL,
                confidence REAL NOT NULL,
                estimated_cost_usd REAL NOT NULL,
                capability_match REAL NOT NULL,
                bid_time DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (task_id) REFERENCES cnp_tasks(task_id)
            );
            CREATE TABLE IF NOT EXISTS cnp_handoffs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id TEXT NOT NULL,
                agent_id TEXT NOT NULL,
                success INTEGER NOT NULL DEFAULT 1,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_bids_task ON cnp_bids(task_id);
            CREATE INDEX IF NOT EXISTS idx_handoffs_agent ON cnp_handoffs(agent_id);
        """)
        conn.commit()

    def announce_task(
        self,
        task_id: str,
        description: str,
        tags: list[str],
        min_confidence: float = 0.5,
    ) -> None:
        """Announce a task to the agent fleet. Idempotent (safe to call twice)."""
        import json

        conn = self.get_conn()
        conn.execute(
            """INSERT OR REPLACE INTO cnp_tasks
               (task_id, description, tags, min_confidence, status, updated_at)
               VALUES (?, ?, ?, ?, 'open', CURRENT_TIMESTAMP)""",
            (task_id, description, json.dumps(tags), min_confidence),
        )
        conn.commit()

    def submit_bid(self, bid: BidEnvelope) -> None:
        """Submit a bid for a task."""
        conn = self.get_conn()
        conn.execute(
            """INSERT INTO cnp_bids
               (task_id, agent_id, confidence, estimated_cost_usd, capability_match)
               VALUES (?, ?, ?, ?, ?)""",
            (bid.task_id, bid.agent_id, bid.confidence,
             bid.estimated_cost_usd, bid.capability_match),
        )
        conn.commit()

    def get_bids(self, task_id: str) -> list[BidEnvelope]:
        """Get all bids for a task."""
        conn = self.get_conn()
        rows = conn.execute(
            """SELECT task_id, agent_id, confidence, estimated_cost_usd, capability_match, bid_time
               FROM cnp_bids WHERE task_id = ?
               ORDER BY id""",
            (task_id,),
        ).fetchall()
        return [
            BidEnvelope(
                agent_id=row["agent_id"],
                task_id=row["task_id"],
                confidence=row["confidence"],
                estimated_cost_usd=row["estimated_cost_usd"],
                capability_match=row["capability_match"],
                bid_time=row["bid_time"],
            )
            for row in rows
        ]

    def award_task(self, task_id: str) -> BidEnvelope | None:
        """Award task to highest-scoring bid. Returns winner or None if no valid bids.

        Scoring: confidence*0.4 + capability_match*0.4 + cost_efficiency*0.2
        where cost_efficiency = 1.0 / max(estimated_cost_usd, 0.001)
        (capped at 1.0 for free tasks)
        """
        bids = self.get_bids(task_id)
        if not bids:
            return None

        # Get min_confidence threshold
        conn = self.get_conn()
        row = conn.execute(
            "SELECT min_confidence FROM cnp_tasks WHERE task_id = ?",
            (task_id,),
        ).fetchone()
        min_conf = row["min_confidence"] if row else 0.5

        best: tuple[float, BidEnvelope] | None = None
        for bid in bids:
            if bid.confidence < min_conf:
                continue
            cost_eff = min(1.0, 1.0 / max(bid.estimated_cost_usd, 0.001))
            score = bid.confidence * 0.4 + bid.capability_match * 0.4 + cost_eff * 0.2
            if best is None or score > best[0]:
                best = (score, bid)

        if best is None:
            return None

        winner = best[1]
        conn.execute(
            "UPDATE cnp_tasks SET status = 'awarded', "
            "updated_at = CURRENT_TIMESTAMP WHERE task_id = ?",
            (task_id,),
        )
        conn.commit()
        return winner

    def get_winner(self, task_id: str) -> BidEnvelope | None:
        """Get current winner (same as award_task but idempotent — no status change)."""
        bids = self.get_bids(task_id)
        if not bids:
            return None

        conn = self.get_conn()
        row = conn.execute(
            "SELECT min_confidence FROM cnp_tasks WHERE task_id = ?",
            (task_id,),
        ).fetchone()
        min_conf = row["min_confidence"] if row else 0.5

        best: tuple[float, BidEnvelope] | None = None
        for bid in bids:
            if bid.confidence < min_conf:
                continue
            cost_eff = min(1.0, 1.0 / max(bid.estimated_cost_usd, 0.001))
            score = bid.confidence * 0.4 + bid.capability_match * 0.4 + cost_eff * 0.2
            if best is None or score > best[0]:
                best = (score, bid)

        return best[1] if best else None

    def record_handoff(self, task_id: str, agent_id: str, success: bool) -> None:
        """Record handoff outcome for reputation tracking."""
        conn = self.get_conn()
        conn.execute(
            """INSERT INTO cnp_handoffs (task_id, agent_id, success)
               VALUES (?, ?, ?)""",
            (task_id, agent_id, int(success)),
        )
        if success:
            conn.execute(
                "UPDATE cnp_tasks SET status = 'completed', "
                "updated_at = CURRENT_TIMESTAMP WHERE task_id = ?",
                (task_id,),
            )
        else:
            conn.execute(
                "UPDATE cnp_tasks SET status = 'failed', "
                "updated_at = CURRENT_TIMESTAMP WHERE task_id = ?",
                (task_id,),
            )
        conn.commit()

    def get_reputation(self, agent_id: str) -> float:
        """Get reputation score for an agent (success rate 0.0-1.0).

        Returns 0.5 for unknown agents (neutral prior).
        """
        conn = self.get_conn()
        row = conn.execute(
            """SELECT
                   COUNT(*) as total,
                   SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END) as successes
               FROM cnp_handoffs
               WHERE agent_id = ?""",
            (agent_id,),
        ).fetchone()

        if row is None or row["total"] == 0:
            return 0.5  # neutral prior for unknown agents

        return float(row["successes"] or 0) / float(row["total"])
