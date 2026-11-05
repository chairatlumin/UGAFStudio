"""Evaluation runner — orchestrates batch scenario execution."""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Callable

from qa_framework.eval.agent_scorer import AgentScorer
from qa_framework.eval.scenario_registry import ScenarioRegistry

DEFAULT_DB_PATH = Path.home() / ".ugafstudio" / "eval.db"


class EvalRunner:
    """Runs agents against scenarios and records results."""

    def __init__(
        self,
        scenario_registry: ScenarioRegistry | None = None,
        agent_scorer: AgentScorer | None = None,
        db_path: str | None = None,
    ) -> None:
        self.db_path = str(db_path) if db_path else str(DEFAULT_DB_PATH)
        self.scenario_registry = scenario_registry or ScenarioRegistry(self.db_path)
        self.agent_scorer = agent_scorer or AgentScorer()
        self._lock = threading.Lock()
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _init_db(self) -> None:
        with self._lock:
            conn = self._connect()
            conn.execute("""
                CREATE TABLE IF NOT EXISTS eval_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    scenario_id INTEGER NOT NULL,
                    agent_id TEXT NOT NULL,
                    timestamp REAL NOT NULL,
                    coverage REAL,
                    bug_detection REAL,
                    consistency REAL,
                    efficiency REAL,
                    composite REAL,
                    trace_json TEXT,
                    cost_json TEXT,
                    FOREIGN KEY(scenario_id) REFERENCES scenarios(id)
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS traces (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    eval_run_id INTEGER NOT NULL,
                    sequence INTEGER NOT NULL,
                    state_hash TEXT,
                    action TEXT,
                    outcome TEXT,
                    reward REAL,
                    timestamp REAL NOT NULL,
                    FOREIGN KEY(eval_run_id) REFERENCES eval_runs(id)
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_eval_runs_scenario ON eval_runs(scenario_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_traces_run ON traces(eval_run_id)")
            conn.commit()
            conn.close()

    def run_scenario(
        self,
        scenario_id: int,
        agent_callable: Callable[[dict], list[dict]],
        n_runs: int = 3,
        agent_id: str = "default",
    ) -> dict:
        """Run an agent against a scenario multiple times. Returns summary."""
        scenario = self.scenario_registry.get(scenario_id)
        all_scores = []
        all_traces = []

        for i in range(n_runs):
            trace = agent_callable(scenario)
            all_traces.append(trace)
            costs = {"time": 30.0 + i * 5, "cost": 0.001 * (i + 1), "complexity": 3}
            score = self.agent_scorer.score_run(scenario, trace, costs)
            all_scores.append(score)
            self._record_run(scenario_id, agent_id, trace, score, costs)

        # Compute consistency across runs
        consistency = self.agent_scorer.compute_consistency(all_traces)
        for s in all_scores:
            s["consistency"] = consistency

        # Recompute composite with updated consistency
        for s in all_scores:
            s["composite"] = self.agent_scorer.composite(
                s["coverage"], s["bug_detection"], consistency, s["efficiency"]
            )

        return {
            "scenario_id": scenario_id,
            "n_runs": n_runs,
            "scores": all_scores,
            "avg_composite": round(sum(s["composite"] for s in all_scores) / len(all_scores), 4),
            "consistency": round(consistency, 4),
        }

    def _record_run(
        self,
        scenario_id: int,
        agent_id: str,
        trace: list[dict],
        score: dict,
        costs: dict,
    ) -> int:
        with self._lock:
            conn = self._connect()
            cursor = conn.execute(
                """INSERT INTO eval_runs (scenario_id, agent_id, timestamp, coverage, bug_detection, consistency, efficiency, composite, trace_json, cost_json)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    scenario_id,
                    agent_id,
                    time.time(),
                    score.get("coverage", 0.0),
                    score.get("bug_detection", 0.0),
                    score.get("consistency", 0.0),
                    score.get("efficiency", 0.0),
                    score.get("composite", 0.0),
                    json.dumps(trace),
                    json.dumps(costs),
                ),
            )
            eval_run_id = cursor.lastrowid or 0

            for seq, step in enumerate(trace):
                conn.execute(
                    """INSERT INTO traces (eval_run_id, sequence, state_hash, action, outcome, reward, timestamp)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (
                        eval_run_id,
                        seq,
                        step.get("state_hash", ""),
                        step.get("action", ""),
                        step.get("outcome", ""),
                        step.get("reward", 0.0),
                        time.time(),
                    ),
                )

            conn.commit()
            conn.close()
            return eval_run_id

    def run_batch(
        self,
        scenario_ids: list[int],
        agent_callable: Callable[[dict], list[dict]],
        n_runs: int = 3,
        agent_id: str = "default",
    ) -> list[dict]:
        """Run agent against multiple scenarios."""
        return [
            self.run_scenario(sid, agent_callable, n_runs, agent_id)
            for sid in scenario_ids
        ]

    def record_trace(
        self,
        eval_run_id: int,
        sequence: int,
        state_hash: str,
        action: str,
        outcome: str,
        reward: float,
    ) -> None:
        """Manually record a trace step for an existing eval run."""
        with self._lock:
            conn = self._connect()
            conn.execute(
                """INSERT INTO traces (eval_run_id, sequence, state_hash, action, outcome, reward, timestamp)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (eval_run_id, sequence, state_hash, action, outcome, reward, time.time()),
            )
            conn.commit()
            conn.close()

    def get_history(self, scenario_id: int, n: int = 10) -> list[dict]:
        """Get recent eval run history for a scenario."""
        conn = self._connect()
        rows = conn.execute(
            """SELECT id, scenario_id, agent_id, timestamp, coverage, bug_detection, consistency, efficiency, composite, cost_json
               FROM eval_runs WHERE scenario_id = ? ORDER BY timestamp DESC LIMIT ?""",
            (scenario_id, n),
        ).fetchall()
        conn.close()
        return [
            {
                "id": r["id"],
                "scenario_id": r["scenario_id"],
                "agent_id": r["agent_id"],
                "timestamp": r["timestamp"],
                "coverage": r["coverage"],
                "bug_detection": r["bug_detection"],
                "consistency": r["consistency"],
                "efficiency": r["efficiency"],
                "composite": r["composite"],
                "costs": json.loads(r["cost_json"] or "{}"),
            }
            for r in rows
        ]
