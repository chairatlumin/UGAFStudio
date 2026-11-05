"""SQLite-backed graph store for cross-run entity relationships."""

from __future__ import annotations

import sqlite3
import time
from typing import List, Optional

from qa_framework.memory_compaction.models import Edge


class GraphStore:
    """SQLite-backed graph store: nodes=entities, edges=relationships."""

    SCHEMA_CREATE = """CREATE TABLE IF NOT EXISTS edges (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        source TEXT NOT NULL,
        target TEXT NOT NULL,
        relation TEXT NOT NULL,
        confidence REAL NOT NULL,
        created_at REAL NOT NULL,
        last_seen REAL NOT NULL
    )"""

    SCHEMA_INDEXES = """CREATE INDEX IF NOT EXISTS idx_edges_source ON edges(source);
        CREATE INDEX IF NOT EXISTS idx_edges_target ON edges(target);
        CREATE INDEX IF NOT EXISTS idx_edges_relation ON edges(relation);"""

    def __init__(self, db_path: str = ":memory:") -> None:
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute(self.SCHEMA_CREATE)
        for stmt in self.SCHEMA_INDEXES.split(';'):
            stmt = stmt.strip()
            if stmt:
                self.conn.execute(stmt)
        self.conn.commit()

    def add_edge(self, source: str, target: str, relation: str, confidence: float = 1.0) -> Edge:
        """Add a graph edge. Returns the created Edge."""
        now = time.time()
        cursor = self.conn.execute(
            "INSERT INTO edges (source, target, relation, confidence, created_at, last_seen) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (source, target, relation, confidence, now, now),
        )
        edge_id = cursor.lastrowid
        self.conn.commit()
        return Edge(
            id=str(edge_id),
            source=source,
            target=target,
            relation=relation,
            confidence=confidence,
            created_at=now,
            last_seen=now,
        )

    def query_neighbors(
        self, entity: str, relation: Optional[str] = None
    ) -> List[Edge]:
        """Query outgoing neighbors from entity, optionally filtered by relation."""
        if relation:
            rows = self.conn.execute(
                "SELECT * FROM edges WHERE source = ? AND relation = ?",
                (entity, relation),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM edges WHERE source = ?",
                (entity,),
            ).fetchall()
        return [Edge(**{col: row[col] for col in row.keys()}) for row in rows]

    def decay_edges(self, max_age_days: int = 30, decay_factor: float = 0.9) -> int:
        """Decay edge confidence for older edges. Returns count of decayed."""
        cutoff = time.time() - (max_age_days * 86400)
        self.conn.execute(
            "UPDATE edges SET confidence = confidence * ?, last_seen = last_seen "
            "WHERE created_at < ? AND confidence > 0",
            (decay_factor, cutoff),
        )
        self.conn.commit()
        return self.conn.total_changes
