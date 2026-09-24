"""Memory quality evaluator: measures whether memory retrieval improvements decisions."""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path
from typing import Any

_DB_DIR = Path(__file__).resolve().parent / ".ugafstudio"
_DB_PATH = _DB_DIR / "memory_eval.db"


class MemoryEvaluator:
    """Tracks decision quality with/without memory and retrieval precision."""

    def __init__(self, db_path: str | None = None) -> None:
        self._db_path = Path(db_path) if db_path else _DB_PATH
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._hierarchy: Any = None
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(str(self._db_path)) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS decisions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT NOT NULL,
                    used_memory BOOLEAN NOT NULL,
                    outcome TEXT NOT NULL,
                    timestamp REAL NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS retrievals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT NOT NULL,
                    retrieved_count INTEGER NOT NULL,
                    relevant_count INTEGER NOT NULL,
                    outcome TEXT NOT NULL,
                    timestamp REAL NOT NULL
                )
            """)

    def accept_span_hierarchy(self, hierarchy: Any) -> None:
        """Inject a SpanHierarchy to emit MEMORY spans on record_decision/record_retrieval."""
        self._hierarchy = hierarchy

    def record_decision(self, task_id: str, used_memory: bool, outcome: str) -> None:
        with sqlite3.connect(str(self._db_path)) as conn:
            conn.execute(
                "INSERT INTO decisions (task_id, used_memory, outcome, timestamp) VALUES (?, ?, ?, ?)",
                (task_id, used_memory, outcome, time.time()),
            )
        if self._hierarchy is not None:
            self._hierarchy.add_memory_span(task_id, used_memory, outcome)

    def record_retrieval(
        self, task_id: str, retrieved: list[str], relevant: list[str], outcome: str
    ) -> None:
        relevant_count = len(set(retrieved) & set(relevant))
        with sqlite3.connect(str(self._db_path)) as conn:
            conn.execute(
                "INSERT INTO retrievals (task_id, retrieved_count, relevant_count, outcome, timestamp) VALUES (?, ?, ?, ?, ?)",
                (task_id, len(retrieved), relevant_count, outcome, time.time()),
            )
        if self._hierarchy is not None:
            self._hierarchy.add_memory_span(task_id, used_memory=True, outcome=outcome)

    def get_stats(self) -> dict[str, Any]:
        with sqlite3.connect(str(self._db_path)) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("SELECT used_memory, outcome FROM decisions").fetchall()
        with_mem = [r for r in rows if r["used_memory"]]
        without_mem = [r for r in rows if not r["used_memory"]]
        return {
            "with_memory": {
                "count": len(with_mem),
                "success_rate": sum(1 for r in with_mem if r["outcome"] == "pass") / len(with_mem)
                if with_mem
                else 0.0,
            },
            "without_memory": {
                "count": len(without_mem),
                "success_rate": sum(1 for r in without_mem if r["outcome"] == "pass")
                / len(without_mem)
                if without_mem
                else 0.0,
            },
        }

    def get_precision(self) -> float:
        with sqlite3.connect(str(self._db_path)) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("SELECT retrieved_count, relevant_count FROM retrievals").fetchall()
        if not rows:
            return 0.0
        total_relevant = sum(r["relevant_count"] for r in rows)
        total_retrieved = sum(r["retrieved_count"] for r in rows)
        return total_relevant / total_retrieved if total_retrieved > 0 else 0.0


class ForgettingScheduler:
    """Archives stale memory entries, respecting keep-forever tags."""

    def __init__(self, max_age_seconds: float = 86400.0 * 30) -> None:
        self.max_age_seconds = max_age_seconds
        self._access_times: dict[str, float] = {}
        self._keep_forever: set[str] = set()

    def record_access(self, key: str) -> None:
        self._access_times[key] = time.time()

    def set_keep_forever(self, key: str) -> None:
        self._keep_forever.add(key)

    def get_archive_candidates(self) -> list[str]:
        now = time.time()
        return [
            key
            for key, last_access in self._access_times.items()
            if key not in self._keep_forever and now - last_access > self.max_age_seconds
        ]
