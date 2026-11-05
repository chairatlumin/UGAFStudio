"""Procedural memory store: reusable action-sequence skills."""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

from qa_framework.utils import ensure_dir

_DB_DIR = Path(__file__).resolve().parent.parent.parent / ".ugafstudio"
_DB_PATH = _DB_DIR / "memory.db"


class ProceduralStore:
    """Stores successful action patterns as reusable skills."""

    def __init__(self, db_path: str | None = None) -> None:
        self._db_path = Path(db_path) if db_path else _DB_PATH
        ensure_dir(self._db_path.parent)
        self._lock = threading.Lock()
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _init_db(self) -> None:
        with self._lock:
            conn = self._connect()
            try:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS procedural (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        name TEXT NOT NULL,
                        preconditions_json TEXT NOT NULL,
                        action_sequence_json TEXT NOT NULL,
                        expected_outcome TEXT NOT NULL,
                        success_count INTEGER DEFAULT 0,
                        fail_count INTEGER DEFAULT 0,
                        created_at REAL NOT NULL
                    )
                """)
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_procedural_name "
                    "ON procedural (name)"
                )
                conn.commit()
            finally:
                conn.close()

    def store_skill(
        self,
        name: str,
        preconditions: dict[str, Any],
        actions: list[str],
        expected_outcome: str,
    ) -> int:
        """Save a successful action pattern. Returns the new row id."""
        with self._lock:
            conn = self._connect()
            try:
                pre_json = json.dumps(preconditions, sort_keys=True)
                act_json = json.dumps(actions)
                cursor = conn.execute(
                    """
                    INSERT INTO procedural
                        (name, preconditions_json, action_sequence_json,
                         expected_outcome, created_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (name, pre_json, act_json, expected_outcome, time.time()),
                )
                conn.commit()
                return int(cursor.lastrowid or 0)
            finally:
                conn.close()

    def find_matching_skills(
        self,
        current_state_hash: str,
        available_actions: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Find skills whose preconditions match the current state hash.

        Precondition keys are checked as substring matches against the state hash.
        If available_actions is provided, only skills whose action_sequence
        uses actions within available_actions are returned.
        """
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT * FROM procedural ORDER BY (success_count - fail_count) DESC"
            ).fetchall()

            results = []
            for row in rows:
                pre = json.loads(row["preconditions_json"])
                actions = json.loads(row["action_sequence_json"])

                if available_actions is not None:
                    if not all(a in available_actions for a in actions):
                        continue

                # Check precondition substring match
                match = True
                for key, val in pre.items():
                    needle = f"{key}={val}"
                    if needle not in current_state_hash:
                        match = False
                        break

                if match:
                    d = dict(row)
                    d["preconditions"] = pre
                    d["action_sequence"] = actions
                    results.append(d)

            return results
        finally:
            conn.close()

    def record_result(self, skill_id: int, success: bool) -> None:
        """Update success/fail counters after a skill is used."""
        with self._lock:
            conn = self._connect()
            try:
                if success:
                    conn.execute(
                        "UPDATE procedural SET success_count = success_count + 1 WHERE id = ?",
                        (skill_id,),
                    )
                else:
                    conn.execute(
                        "UPDATE procedural SET fail_count = fail_count + 1 WHERE id = ?",
                        (skill_id,),
                    )
                conn.commit()
            finally:
                conn.close()

    def get_top_skills(self, n: int = 5) -> list[dict[str, Any]]:
        """Return the top N skills by net success count (success - fail)."""
        conn = self._connect()
        try:
            rows = conn.execute(
                """
                SELECT *, (success_count - fail_count) AS net_success
                FROM procedural
                ORDER BY net_success DESC
                LIMIT ?
                """,
                (n,),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def get_skill_by_id(self, skill_id: int) -> dict[str, Any] | None:
        """Fetch a single skill by id."""
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT * FROM procedural WHERE id = ?", (skill_id,)
            ).fetchone()
            if row is None:
                return None
            d = dict(row)
            d["preconditions"] = json.loads(d["preconditions_json"])
            d["action_sequence"] = json.loads(d["action_sequence_json"])
            return d
        finally:
            conn.close()
