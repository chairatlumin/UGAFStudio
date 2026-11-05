from __future__ import annotations

import sqlite3
import time
from typing import Optional


class WorkspaceLocker:
    """SQLite-backed file lock registry for cross-agent race prevention.

    Uses WAL journal mode for cross-platform stability.
    Auto-expires stale locks on every acquire attempt.
    Re-entrant for the same agent_id (extends timeout).
    """

    def __init__(self, db_path: str = ".ai/a2a/locks.db") -> None:
        self.db_path = db_path
        self._conn = sqlite3.connect(self.db_path)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS file_locks (
                path TEXT PRIMARY KEY,
                agent_id TEXT NOT NULL,
                acquired_at REAL NOT NULL,
                expires_at REAL NOT NULL
            )
            """
        )
        self._conn.commit()

    # ── public API ──────────────────────────────────────────────────────

    def acquire_lock(self, agent_id: str, file_path: str, timeout: float = 30.0) -> bool:
        """Acquire a lock on *file_path* for *agent_id*.

        Stale locks (expired) are automatically released.
        Re-entrant: if the same agent already holds the lock, the timeout is extended.

        Returns True if the lock was acquired, False if the timeout elapsed.
        """
        now = time.time()
        # Auto-expire stale locks first
        self._conn.execute(
            "DELETE FROM file_locks WHERE expires_at <= ?", (now,)
        )
        self._conn.commit()

        # Check if same agent already holds the lock (re-entrant)
        row = self._conn.execute(
            "SELECT agent_id, expires_at FROM file_locks WHERE path = ?",
            (file_path,),
        ).fetchone()

        if row and row[1] > now:
            # Lock is held and not expired; check if same agent
            if row[0] == agent_id:
                # Re-entrant: extend timeout
                self._conn.execute(
                    "UPDATE file_locks SET expires_at = ? WHERE path = ?",
                    (now + timeout, file_path),
                )
                self._conn.commit()
                return True
            # Different agent holds the lock
            return False

        # Acquire or replace the lock
        self._conn.execute(
            """
            INSERT OR REPLACE INTO file_locks (path, agent_id, acquired_at, expires_at)
            VALUES (?, ?, ?, ?)
            """,
            (file_path, agent_id, now, now + timeout),
        )
        self._conn.commit()
        return True

    def release_lock(self, agent_id: str, file_path: str) -> None:
        """Release the lock on *file_path* for *agent_id*."""
        self._conn.execute(
            "DELETE FROM file_locks WHERE path = ? AND agent_id = ?",
            (file_path, agent_id),
        )
        self._conn.commit()

    def get_lock_holder(self, file_path: str) -> Optional[str]:
        """Return the agent_id holding the lock, or None if unlocked/expired."""
        row = self._conn.execute(
            "SELECT agent_id FROM file_locks WHERE path = ? AND expires_at > ?",
            (file_path, time.time()),
        ).fetchone()
        return row[0] if row else None

    # ── cleanup ──────────────────────────────────────────────────────────

    def close(self) -> None:
        self._conn.close()
