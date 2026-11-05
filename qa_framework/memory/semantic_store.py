"""Semantic memory store: consolidated facts with confidence scoring."""

from __future__ import annotations

import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

from qa_framework.memory.episodic_store import EpisodicStore
from qa_framework.utils import ensure_dir

_DB_DIR = Path(__file__).resolve().parent.parent.parent / ".ugafstudio"
_DB_PATH = _DB_DIR / "memory.db"


class SemanticStore:
    """Consolidated facts about game state with confidence scoring and deduplication."""

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
                    CREATE TABLE IF NOT EXISTS semantic (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        key TEXT UNIQUE NOT NULL,
                        value TEXT NOT NULL,
                        confidence REAL DEFAULT 0.5,
                        corroborations INTEGER DEFAULT 0,
                        contradicted INTEGER DEFAULT 0,
                        created_at REAL NOT NULL,
                        updated_at REAL NOT NULL
                    )
                """)
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_semantic_confidence "
                    "ON semantic (confidence DESC)"
                )
                conn.commit()
            finally:
                conn.close()

    def upsert_fact(self, key: str, value: str, confidence: float = 0.5) -> None:
        """Insert a new fact or update confidence if key already exists."""
        with self._lock:
            conn = self._connect()
            try:
                existing = conn.execute(
                    "SELECT id, confidence, corroborations FROM semantic WHERE key = ?",
                    (key,),
                ).fetchone()
                now = time.time()
                if existing:
                    new_conf = min(1.0, existing["confidence"] + 0.1)
                    new_corr = existing["corroborations"] + 1
                    conn.execute(
                        """
                        UPDATE semantic
                        SET value = ?, confidence = ?, corroborations = ?, updated_at = ?
                        WHERE id = ?
                        """,
                        (value, new_conf, new_corr, now, existing["id"]),
                    )
                else:
                    conn.execute(
                        """
                        INSERT INTO semantic
                            (key, value, confidence, corroborations, contradicted,
                             created_at, updated_at)
                        VALUES (?, ?, ?, 0, 0, ?, ?)
                        """,
                        (key, value, confidence, now, now),
                    )
                conn.commit()
            finally:
                conn.close()

    def corroborate(self, key: str, delta: float = 0.1) -> None:
        """Increase confidence for an existing fact."""
        with self._lock:
            conn = self._connect()
            try:
                conn.execute(
                    """
                    UPDATE semantic
                    SET confidence = MIN(1.0, confidence + ?),
                        corroborations = corroborations + 1,
                        updated_at = ?
                    WHERE key = ?
                    """,
                    (delta, time.time(), key),
                )
                conn.commit()
            finally:
                conn.close()

    def contradict(self, key: str) -> None:
        """Mark a fact as contradicted for later review."""
        with self._lock:
            conn = self._connect()
            try:
                conn.execute(
                    """
                    UPDATE semantic
                    SET contradicted = contradicted + 1,
                        confidence = MAX(0.0, confidence - 0.2),
                        updated_at = ?
                    WHERE key = ?
                    """,
                    (time.time(), key),
                )
                conn.commit()
            finally:
                conn.close()

    def query_facts(self, key_pattern: str) -> list[dict[str, Any]]:
        """Retrieve facts whose key matches a LIKE pattern."""
        conn = self._connect()
        try:
            rows = conn.execute(
                """
                SELECT * FROM semantic
                WHERE key LIKE ?
                ORDER BY confidence DESC
                """,
                (f"%{key_pattern}%",),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def consolidate_from_episodic(
        self, episodic: EpisodicStore, session_id: str
    ) -> int:
        """Consolidate raw episodic logs into semantic facts.

        Groups by state_hash, extracts unique (action, outcome) pairs,
        and upserts them as facts.
        """
        records = episodic.get_session_records(session_id)
        if not records:
            return 0

        facts_added = 0
        seen: set[tuple[str, str]] = set()
        for row in records:
            sh = row["state_hash"]
            act = row["action"]
            dedup_key = (sh, act)
            if dedup_key in seen:
                continue
            seen.add(dedup_key)

            fact_value = f"action={act}|outcome={row['outcome']}|reward={row['reward']}"
            key = f"game_state:{sh}:{act}"
            self.upsert_fact(key, fact_value, confidence=0.6)
            facts_added += 1

        return facts_added

    def get_all_facts(self) -> list[dict[str, Any]]:
        """Return all semantic facts ordered by confidence descending."""
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT * FROM semantic ORDER BY confidence DESC"
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()
