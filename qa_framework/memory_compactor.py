"""Four-tier memory compaction for long agent sessions."""
from __future__ import annotations

import hashlib
import sqlite3
import time
from enum import IntEnum
from pathlib import Path


class MemoryTier(IntEnum):
    WORKING = 0    # Current turn buffer (small, fast)
    EPISODIC = 1   # Session history (last N interactions)
    SEMANTIC = 2   # Extracted facts and knowledge
    ARCHIVAL = 3   # Compressed summaries, old data


class MemoryCompactor:
    """Four-tier memory with automatic compaction."""

    def __init__(
        self,
        db_path: str = ".ai/a2a/memory.db",
        working_buffer_size: int = 50,
        episodic_limit: int = 500,
    ) -> None:
        if db_path != ":memory:":
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._working_size = working_buffer_size
        self._episodic_limit = episodic_limit
        self._create_tables()

    def _create_tables(self) -> None:
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS memories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                content TEXT NOT NULL,
                tier INTEGER NOT NULL DEFAULT 0,
                hash TEXT NOT NULL,
                created_at REAL NOT NULL DEFAULT (strftime('%s', 'now'))
            );
            CREATE INDEX IF NOT EXISTS idx_memories_session ON memories(session_id);
            CREATE INDEX IF NOT EXISTS idx_memories_tier ON memories(tier);
            CREATE INDEX IF NOT EXISTS idx_memories_created ON memories(created_at);
        """)
        self._conn.commit()

    def _hash(self, content: str) -> str:
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    def add_memory(
        self, session_id: str, content: str, tier: MemoryTier = MemoryTier.WORKING
    ) -> int:
        """Add a memory entry at the specified tier."""
        h = self._hash(content)
        with self._conn:
            # Dedup: skip if same content already exists at this tier or higher
            existing = self._conn.execute(
                """SELECT id, tier FROM memories
                   WHERE session_id = ? AND hash = ? AND tier <= ?""",
                (session_id, h, int(tier)),
            ).fetchone()
            if existing:
                return int(existing["id"])

            cur = self._conn.execute(
                """INSERT INTO memories (session_id, content, tier, hash, created_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (session_id, content, int(tier), h, time.time()),
            )
            # Check if working buffer needs compaction
            if tier == MemoryTier.WORKING:
                self._maybe_compact(session_id)
            lastrowid = cur.lastrowid
            if lastrowid is None:
                raise RuntimeError("Failed to insert memory")
            return int(lastrowid)

    def _maybe_compact(self, session_id: str) -> None:
        """Compact working buffer to episodic if full."""
        count = self._conn.execute(
            "SELECT COUNT(*) FROM memories WHERE session_id = ? AND tier = ?",
            (session_id, int(MemoryTier.WORKING)),
        ).fetchone()[0]

        if count > self._working_size:
            # Move oldest working memories to episodic
            to_move = count - self._working_size
            self._conn.execute(
                """UPDATE memories SET tier = ?
                   WHERE id IN (
                       SELECT id FROM memories
                       WHERE session_id = ? AND tier = ?
                       ORDER BY created_at ASC LIMIT ?
                   )""",
                (int(MemoryTier.EPISODIC), session_id, int(MemoryTier.WORKING), to_move),
            )
            self._conn.commit()

    def promote(self, session_id: str, content: str, new_tier: MemoryTier) -> bool:
        """Promote a memory to a higher tier."""
        h = self._hash(content)
        with self._conn:
            cur = self._conn.execute(
                """UPDATE memories SET tier = ? WHERE session_id = ? AND hash = ? AND tier < ?""",
                (int(new_tier), session_id, h, int(new_tier)),
            )
            return cur.rowcount > 0

    def query(
        self,
        session_id: str,
        tier: MemoryTier | None = None,
        limit: int = 50,
    ) -> list[dict]:
        """Query memories for a session, optionally filtered by tier."""
        if tier is not None:
            rows = self._conn.execute(
                """SELECT id, session_id, content, tier, created_at FROM memories
                   WHERE session_id = ? AND tier = ?
                   ORDER BY created_at DESC LIMIT ?""",
                (session_id, int(tier), limit),
            ).fetchall()
        else:
            rows = self._conn.execute(
                """SELECT id, session_id, content, tier, created_at FROM memories
                   WHERE session_id = ?
                   ORDER BY tier ASC, created_at DESC LIMIT ?""",
                (session_id, limit),
            ).fetchall()
        return [dict(r) for r in rows]

    def get_working_set(self, session_id: str) -> list[dict]:
        """Get the current working buffer."""
        return self.query(session_id, tier=MemoryTier.WORKING, limit=self._working_size)

    def flush_episodic_to_semantic(self, session_id: str) -> int:
        """Move all episodic memories to semantic (compaction)."""
        with self._conn:
            cur = self._conn.execute(
                "UPDATE memories SET tier = ? WHERE session_id = ? AND tier = ?",
                (int(MemoryTier.SEMANTIC), session_id, int(MemoryTier.EPISODIC)),
            )
            return cur.rowcount

    def prune_archival(self, max_age_days: int = 30) -> int:
        """Remove old archival memories."""
        cutoff = time.time() - (max_age_days * 86400)
        with self._conn:
            cur = self._conn.execute(
                "DELETE FROM memories WHERE tier = ? AND created_at < ?",
                (int(MemoryTier.ARCHIVAL), cutoff),
            )
            return cur.rowcount

    def stats(self, session_id: str) -> dict[str, int]:
        """Get memory tier counts for a session."""
        rows = self._conn.execute(
            """SELECT tier, COUNT(*) as count FROM memories
               WHERE session_id = ? GROUP BY tier ORDER BY tier""",
            (session_id,),
        ).fetchall()
        result = {tier.name: 0 for tier in MemoryTier}
        for r in rows:
            tier_name = MemoryTier(r["tier"]).name
            result[tier_name] = r["count"]
        return result
