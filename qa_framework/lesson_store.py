"""Shared Agent Memory Graph — SQLite lesson storage with Jaccard similarity search."""

from __future__ import annotations

import json
import re
import sqlite3
import threading
from dataclasses import asdict, dataclass
from typing import Any

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _tokens(text: str) -> set[str]:
    return set(_TOKEN_RE.findall(text.lower()))


@dataclass
class Lesson:
    id: int
    agent_id: str
    pattern: str
    solution: str
    tags: list[str]
    confidence: float
    created_at: str
    hit_count: int


class LessonStore:
    """SQLite backend for resolved bug/pattern lessons.

    Thread-safe via WAL mode and per-thread connections (same pattern as FleetRecorder).
    """

    def __init__(self, db_path: str = ":memory:") -> None:
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
            CREATE TABLE IF NOT EXISTS lessons (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                agent_id TEXT NOT NULL,
                pattern TEXT NOT NULL,
                solution TEXT NOT NULL,
                tags TEXT NOT NULL DEFAULT '[]',
                confidence REAL DEFAULT 1.0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                hit_count INTEGER NOT NULL DEFAULT 0
            );
            CREATE INDEX IF NOT EXISTS idx_lessons_agent ON lessons(agent_id);
        """)
        conn.commit()

    def add_lesson(
        self,
        agent_id: str,
        pattern: str,
        solution: str,
        tags: list[str],
        confidence: float = 1.0,
    ) -> int:
        if not pattern.strip():
            raise ValueError("pattern must be non-empty")
        if not solution.strip():
            raise ValueError("solution must be non-empty")
        if not 0.0 <= confidence <= 1.0:
            raise ValueError("confidence must be in [0, 1]")
        conn = self.get_conn()
        cursor = conn.execute(
            "INSERT INTO lessons (agent_id, pattern, solution, tags, confidence)"
            " VALUES (?, ?, ?, ?, ?)",
            (agent_id, pattern, solution, json.dumps(tags), confidence),
        )
        conn.commit()
        return int(cursor.lastrowid or 0)

    def get_lesson(self, lesson_id: int) -> dict[str, Any] | None:
        conn = self.get_conn()
        row = conn.execute("SELECT * FROM lessons WHERE id = ?", (lesson_id,)).fetchone()
        if row is None:
            return None
        return self._row_to_dict(row)

    def find_similar(
        self,
        query: str,
        limit: int = 5,
        tags: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        # ponytail: full-table Jaccard scan, no vector DB; add FTS5 index past ~10k rows.
        query_tokens = _tokens(query)
        if not query_tokens:
            return []
        wanted = {t.lower() for t in tags} if tags else None
        conn = self.get_conn()
        scored: list[tuple[float, dict[str, Any]]] = []
        for row in conn.execute("SELECT * FROM lessons").fetchall():
            lesson = self._row_to_dict(row)
            if wanted is not None and wanted.isdisjoint(t.lower() for t in lesson["tags"]):
                continue
            pattern_tokens = _tokens(str(lesson["pattern"]))
            union = query_tokens | pattern_tokens
            if not union:
                continue
            score = len(query_tokens & pattern_tokens) / len(union)
            if score > 0:
                lesson["score"] = round(score, 4)
                scored.append((score, lesson))
        scored.sort(key=lambda item: item[0], reverse=True)
        return [lesson for _, lesson in scored[:limit]]

    def record_hit(self, lesson_id: int) -> int:
        conn = self.get_conn()
        conn.execute("UPDATE lessons SET hit_count = hit_count + 1 WHERE id = ?", (lesson_id,))
        conn.commit()
        row = conn.execute("SELECT hit_count FROM lessons WHERE id = ?", (lesson_id,)).fetchone()
        return int(row["hit_count"]) if row is not None else 0

    def get_stats(self) -> dict[str, Any]:
        conn = self.get_conn()
        row = conn.execute(
            "SELECT COUNT(*) as total, COALESCE(SUM(hit_count), 0) as hits,"
            " COALESCE(AVG(confidence), 0.0) as avg_conf FROM lessons"
        ).fetchone()
        agents = conn.execute("SELECT DISTINCT agent_id FROM lessons ORDER BY agent_id").fetchall()
        return {
            "total_lessons": row["total"],
            "total_hits": row["hits"],
            "avg_confidence": round(row["avg_conf"] or 0.0, 4),
            "agents": [r["agent_id"] for r in agents],
        }

    @staticmethod
    def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
        lesson = Lesson(
            id=row["id"],
            agent_id=row["agent_id"],
            pattern=row["pattern"],
            solution=row["solution"],
            tags=json.loads(row["tags"]),
            confidence=row["confidence"],
            created_at=str(row["created_at"]),
            hit_count=row["hit_count"],
        )
        return dict(asdict(lesson))
