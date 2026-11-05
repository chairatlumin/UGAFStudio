"""Episodic memory store: raw interaction logs from game sessions."""

from __future__ import annotations

import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

from qa_framework.utils import ensure_dir

_DB_DIR = Path(__file__).resolve().parent.parent.parent / ".ugafstudio"
_DB_PATH = _DB_DIR / "memory.db"


class EpisodicStore:
    """Stores raw game interaction tuples (state, action, outcome, reward)."""

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
                    CREATE TABLE IF NOT EXISTS episodic (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        session_id TEXT NOT NULL,
                        timestamp REAL NOT NULL,
                        state_hash TEXT NOT NULL,
                        action TEXT NOT NULL,
                        outcome TEXT NOT NULL,
                        reward REAL NOT NULL,
                        raw_state_json TEXT
                    )
                """)
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_episodic_session "
                    "ON episodic (session_id)"
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_episodic_state "
                    "ON episodic (state_hash)"
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_episodic_action "
                    "ON episodic (action)"
                )
                conn.commit()
            finally:
                conn.close()

    def record(
        self,
        session_id: str,
        state_hash: str,
        action: str,
        outcome: str,
        reward: float,
        raw_state_json: str = "",
    ) -> int:
        """Append an interaction log row. Returns the new row id."""
        with self._lock:
            conn = self._connect()
            try:
                cursor = conn.execute(
                    """
                    INSERT INTO episodic
                        (session_id, timestamp, state_hash, action, outcome, reward, raw_state_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (session_id, time.time(), state_hash, action, outcome, reward, raw_state_json),
                )
                conn.commit()
                return int(cursor.lastrowid or 0)
            finally:
                conn.close()

    def get_recent(self, n: int = 50) -> list[dict[str, Any]]:
        """Return the N most recent interaction records."""
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT * FROM episodic ORDER BY timestamp DESC LIMIT ?",
                (n,),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def get_by_action(self, action: str, limit: int = 20) -> list[dict[str, Any]]:
        """Return records matching a specific action."""
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT * FROM episodic WHERE action = ? ORDER BY timestamp DESC LIMIT ?",
                (action, limit),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def get_by_state(self, state_hash: str) -> list[dict[str, Any]]:
        """Return records matching a specific game state hash."""
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT * FROM episodic WHERE state_hash = ? ORDER BY timestamp ASC",
                (state_hash,),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def prune(self, older_than_sessions: int = 7) -> int:
        """Delete episodic records from sessions older than N most recent unique sessions."""
        with self._lock:
            conn = self._connect()
            try:
                rows = conn.execute(
                    "SELECT DISTINCT session_id FROM episodic "
                    "ORDER BY timestamp DESC LIMIT ?",
                    (older_than_sessions,),
                ).fetchall()
                if not rows:
                    return 0
                latest = [r[0] for r in rows]
                placeholders = ",".join("?" for _ in latest)
                cursor = conn.execute(
                    f"DELETE FROM episodic WHERE session_id NOT IN ({placeholders})",
                    latest,
                )
                conn.commit()
                return int(cursor.rowcount or 0)
            finally:
                conn.close()

    def get_session_records(self, session_id: str) -> list[dict[str, Any]]:
        """Return all records for a specific session."""
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT * FROM episodic WHERE session_id = ? ORDER BY timestamp ASC",
                (session_id,),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def count_sessions(self) -> int:
        """Return the number of unique sessions in the store."""
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT COUNT(DISTINCT session_id) FROM episodic"
            ).fetchone()
            return int(row[0] if row else 0)
        finally:
            conn.close()
