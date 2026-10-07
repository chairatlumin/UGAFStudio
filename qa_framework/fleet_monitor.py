"""Fleet-wide observability for UGAFStudio QA — tracks all agent dispatches."""

from __future__ import annotations

import sqlite3
import threading
import time
from typing import Any


class FleetRecorder:
    """SQLite-based fleet-wide observability backend.

    Records every dispatch event across all agents for aggregate analysis.
    Thread-safe via WAL mode and per-thread connections.
    """

    def __init__(self, db_path: str = ".ai/a2a/fleet.db") -> None:
        self.db_path = db_path
        self._local = threading.local()
        self._init_db()

    def get_conn(self) -> sqlite3.Connection:
        """Get a per-thread SQLite connection."""
        if not hasattr(self._local, "conn") or self._local.conn is None:
            conn = sqlite3.connect(self.db_path, timeout=30)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=5000")
            conn.row_factory = sqlite3.Row
            self._local.conn = conn
        return self._local.conn  # type: ignore[no-any-return]

    def close(self) -> None:
        """Close the per-thread connection (required for tempfile cleanup on Windows)."""
        if hasattr(self._local, "conn") and self._local.conn is not None:
            self._local.conn.close()
            self._local.conn = None

    def _init_db(self) -> None:
        """Create tables and indexes if they don't exist."""
        conn = self.get_conn()
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS dispatch_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                agent_id TEXT NOT NULL,
                task_type TEXT NOT NULL,
                model TEXT NOT NULL,
                success INTEGER NOT NULL,
                duration_ms INTEGER NOT NULL,
                cost_usd REAL DEFAULT 0.0,
                confidence REAL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_agent_id ON dispatch_events(agent_id);
            CREATE INDEX IF NOT EXISTS idx_timestamp ON dispatch_events(timestamp);
        """)
        conn.commit()

    def record_dispatch(
        self,
        agent_id: str,
        task_type: str,
        model: str,
        success: bool,
        duration_ms: int,
        cost_usd: float = 0.0,
        confidence: float | None = None,
    ) -> int:
        """Record a dispatch event. Returns the row ID."""
        conn = self.get_conn()
        cursor = conn.execute(
            """INSERT INTO dispatch_events
               (agent_id, task_type, model, success, duration_ms, cost_usd, confidence)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (agent_id, task_type, model, int(success), duration_ms, cost_usd, confidence),
        )
        conn.commit()
        return int(cursor.lastrowid or 0)

    def get_agent_metrics(self, agent_id: str) -> dict[str, Any]:
        """Get metrics for a single agent."""
        conn = self.get_conn()
        row = conn.execute(
            """SELECT
                   COUNT(*) as total_dispatches,
                   SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END) as successes,
                   AVG(duration_ms) as avg_latency_ms,
                   AVG(cost_usd) as avg_cost_usd,
                   SUM(cost_usd) as total_cost_usd,
                   AVG(confidence) as avg_confidence
               FROM dispatch_events
               WHERE agent_id = ?""",
            (agent_id,),
        ).fetchone()

        if row is None or row["total_dispatches"] == 0:
            return {
                "agent_id": agent_id,
                "total_dispatches": 0,
                "success_rate": 0.0,
                "avg_latency_ms": 0.0,
                "avg_cost_usd": 0.0,
                "total_cost_usd": 0.0,
                "avg_confidence": 0.0,
            }

        total = row["total_dispatches"]
        successes = row["successes"] or 0
        return {
            "agent_id": agent_id,
            "total_dispatches": total,
            "success_rate": successes / total if total > 0 else 0.0,
            "avg_latency_ms": round(row["avg_latency_ms"] or 0.0, 2),
            "avg_cost_usd": round(row["avg_cost_usd"] or 0.0, 6),
            "total_cost_usd": round(row["total_cost_usd"] or 0.0, 6),
            "avg_confidence": round(row["avg_confidence"] or 0.0, 4),
        }

    def get_all_agents(self) -> list[str]:
        """Get list of all known agent IDs."""
        conn = self.get_conn()
        rows = conn.execute(
            "SELECT DISTINCT agent_id FROM dispatch_events ORDER BY agent_id"
        ).fetchall()
        return [row["agent_id"] for row in rows]

    def prune_old_records(self, max_age_days: int = 30) -> int:
        """Remove records older than max_age_days. Returns count of deleted rows."""
        conn = self.get_conn()
        cursor = conn.execute(
            "DELETE FROM dispatch_events WHERE timestamp < datetime('now', ?)",
            (f"-{max_age_days} days",),
        )
        conn.commit()
        return int(cursor.rowcount or 0)


class FleetMonitor:
    """Aggregate query layer with anomaly detection for the agent fleet."""

    def __init__(self, recorder: FleetRecorder) -> None:
        self._recorder = recorder

    def get_fleet_summary(self) -> dict[str, Any]:
        """Get fleet-wide aggregate metrics."""
        conn = self._recorder.get_conn()
        row = conn.execute(
            """SELECT
                   COUNT(DISTINCT agent_id) as total_agents,
                   COUNT(*) as total_dispatches,
                   SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END) as total_successes,
                   AVG(duration_ms) as avg_latency_ms,
                   SUM(cost_usd) as total_cost_usd
               FROM dispatch_events"""
        ).fetchone()

        total_dispatches = row["total_dispatches"] or 0
        total_successes = row["total_successes"] or 0
        agents = self._recorder.get_all_agents()

        return {
            "total_agents": row["total_agents"] or 0,
            "total_dispatches": total_dispatches,
            "fleet_success_rate": round(total_successes / total_dispatches, 4)
            if total_dispatches > 0
            else 0.0,
            "total_cost_usd": round(row["total_cost_usd"] or 0.0, 6),
            "avg_latency_ms": round(row["avg_latency_ms"] or 0.0, 2),
            "agents": agents,
        }

    def get_anomalies(
        self, max_error_rate: float = 0.3, min_samples: int = 5
    ) -> list[dict[str, Any]]:
        """Find agents with anomalously high error rates."""
        conn = self._recorder.get_conn()
        rows = conn.execute(
            """SELECT
                   agent_id,
                   COUNT(*) as total,
                   AVG(CAST(success AS FLOAT)) as success_rate,
                   AVG(duration_ms) as avg_latency_ms
               FROM dispatch_events
               GROUP BY agent_id
               HAVING COUNT(*) >= ? AND (1.0 - AVG(CAST(success AS FLOAT))) > ?
               ORDER BY success_rate ASC""",
            (min_samples, max_error_rate),
        ).fetchall()

        return [
            {
                "agent_id": row["agent_id"],
                "error_rate": round(1.0 - (row["success_rate"] or 0.0), 4),
                "total_dispatches": row["total"],
                "avg_latency_ms": round(row["avg_latency_ms"] or 0.0, 2),
            }
            for row in rows
        ]

    def get_top_cost_agents(self, limit: int = 5) -> list[dict[str, Any]]:
        """Get agents ranked by total cost (highest first)."""
        conn = self._recorder.get_conn()
        rows = conn.execute(
            """SELECT
                   agent_id,
                   SUM(cost_usd) as total_cost,
                   COUNT(*) as dispatches,
                   AVG(CAST(success AS FLOAT)) as success_rate
               FROM dispatch_events
               GROUP BY agent_id
               ORDER BY total_cost DESC
               LIMIT ?""",
            (limit,),
        ).fetchall()

        return [
            {
                "agent_id": row["agent_id"],
                "total_cost_usd": round(row["total_cost"] or 0.0, 6),
                "dispatches": row["dispatches"],
                "success_rate": round(row["success_rate"] or 0.0, 4),
            }
            for row in rows
        ]

    def get_latency_percentiles(self, agent_id: str) -> dict[str, float]:
        """Get latency percentiles (p50, p90, p95, p99) for an agent."""
        conn = self._recorder.get_conn()
        rows = conn.execute(
            """SELECT duration_ms FROM dispatch_events
               WHERE agent_id = ?
               ORDER BY duration_ms""",
            (agent_id,),
        ).fetchall()

        latencies = sorted([int(r["duration_ms"]) for r in rows])
        n = len(latencies)
        if n == 0:
            return {"p50": 0.0, "p90": 0.0, "p95": 0.0, "p99": 0.0}

        def percentile(p: float) -> float:
            k = (p / 100.0) * (n - 1)
            f = int(k)
            c = f + 1
            if c >= n:
                return float(latencies[-1])
            d = k - f
            return float(latencies[f]) + d * (float(latencies[c]) - float(latencies[f]))

        return {
            "p50": round(percentile(50), 2),
            "p90": round(percentile(90), 2),
            "p95": round(percentile(95), 2),
            "p99": round(percentile(99), 2),
        }

    def generate_health_report(self) -> dict[str, Any]:
        """Generate comprehensive health report."""
        summary = self.get_fleet_summary()
        anomalies = self.get_anomalies()
        top_cost = self.get_top_cost_agents()
        return {
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "summary": summary,
            "anomalies": anomalies,
            "top_cost_agents": top_cost,
            "healthy_agents": len(summary["agents"]) - len(anomalies),
            "alerts": [
                {
                    "severity": "warning",
                    "message": f"Agent {a['agent_id']} has {a['error_rate']:.0%} error rate",
                }
                for a in anomalies
            ],
        }
