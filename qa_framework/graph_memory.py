"""SQLite-backed graph memory store for cross-agent learning."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta
from typing import Optional

__all__ = ["GraphMemoryStore"]


class GraphMemoryStore:
    """SQLite-backed graph: nodes (entities) + edges (relationships)."""

    SCHEMA = """
    CREATE TABLE IF NOT EXISTS nodes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        entity_type TEXT NOT NULL,
        name TEXT NOT NULL,
        metadata TEXT,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        UNIQUE(entity_type, name)
    );

    CREATE TABLE IF NOT EXISTS edges (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        source_id INTEGER NOT NULL,
        target_id INTEGER NOT NULL,
        relation TEXT NOT NULL,
        confidence REAL DEFAULT 1.0,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        FOREIGN KEY(source_id) REFERENCES nodes(id),
        FOREIGN KEY(target_id) REFERENCES nodes(id),
        UNIQUE(source_id, target_id, relation)
    );

    CREATE INDEX IF NOT EXISTS idx_nodes_type ON nodes(entity_type);
    CREATE INDEX IF NOT EXISTS idx_nodes_name ON nodes(name);
    CREATE INDEX IF NOT EXISTS idx_edges_relation ON edges(relation);
    """

    def __init__(self, db_path: str = ":memory:") -> None:
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(self.SCHEMA)
        self.conn.commit()

    def add_node(
        self, entity_type: str, name: str, metadata: Optional[dict] = None
    ) -> int:
        meta_s = json.dumps(metadata) if metadata is not None else None
        with self.conn:
            cur = self.conn.execute(
                """
                INSERT INTO nodes (entity_type, name, metadata, created_at)
                VALUES (?, ?, ?, datetime('now'))
                ON CONFLICT(entity_type, name)
                DO UPDATE SET metadata = excluded.metadata
                RETURNING id
                """,
                (entity_type, name, meta_s),
            )
            return cur.fetchone()["id"]

    def add_edge(
        self,
        source_id: int,
        target_id: int,
        relation: str,
        confidence: float = 1.0,
    ) -> int:
        with self.conn:
            cur = self.conn.execute(
                """
                INSERT INTO edges (source_id, target_id, relation, confidence, created_at)
                VALUES (?, ?, ?, ?, datetime('now'))
                ON CONFLICT(source_id, target_id, relation)
                DO UPDATE SET confidence = excluded.confidence, created_at = datetime('now')
                RETURNING id
                """,
                (source_id, target_id, relation, confidence),
            )
            return cur.fetchone()["id"]

    def query_related(
        self, entity_name: str, relation: Optional[str] = None
    ) -> list[dict]:
        if relation:
            rows = self.conn.execute(
                """
                SELECT n2.id, n2.entity_type AS type, n2.name, e.relation, e.confidence
                FROM edges e
                JOIN nodes n1 ON n1.id = e.source_id
                JOIN nodes n2 ON n2.id = e.target_id
                WHERE n1.name = ? AND e.relation = ?
                """,
                (entity_name, relation),
            ).fetchall()
        else:
            rows = self.conn.execute(
                """
                SELECT n2.id, n2.entity_type AS type, n2.name, e.relation, e.confidence
                FROM edges e
                JOIN nodes n1 ON n1.id = e.source_id
                JOIN nodes n2 ON n2.id = e.target_id
                WHERE n1.name = ?
                """,
                (entity_name,),
            ).fetchall()
        return [dict(r) for r in rows]

    def query_by_type(self, entity_type: str) -> list[dict]:
        rows = self.conn.execute(
            "SELECT id, entity_type AS type, name, metadata, created_at FROM nodes WHERE entity_type = ?",
            (entity_type,),
        ).fetchall()
        return [dict(r) for r in rows]

    def query_neighbors(self, entity_name: str, hops: int = 2) -> list[dict]:
        """BFS traversal up to N hops from entity."""
        visited: set[int] = set()
        current: set[int] = set()

        row = self.conn.execute(
            "SELECT id FROM nodes WHERE name = ?", (entity_name,)
        ).fetchone()
        if row is None:
            return []
        current.add(row["id"])
        visited.add(row["id"])

        for _ in range(hops):
            if not current:
                break
            cur_placeholders = ",".join("?" * len(current))
            vis_placeholders = ",".join("?" * len(visited))
            rows = self.conn.execute(
                f"""
                SELECT DISTINCT n2.id, n2.entity_type AS type, n2.name
                FROM edges e
                JOIN nodes n2 ON (n2.id = e.target_id OR n2.id = e.source_id)
                WHERE (e.source_id IN ({cur_placeholders}) OR e.target_id IN ({cur_placeholders}))
                AND n2.id NOT IN ({vis_placeholders})
                """,
                (*current, *current, *visited),
            ).fetchall()
            next_level = {r["id"] for r in rows}
            current = next_level - visited
            visited |= next_level
        result = []
        if visited:
            placeholders = ",".join("?" * len(visited))
            rows = self.conn.execute(
                f"SELECT id, entity_type AS type, name FROM nodes WHERE id IN ({placeholders})",
                (*visited,),
            ).fetchall()
            result = [dict(r) for r in rows]
        return result

    def decay_edges(self, max_age_days: int = 30) -> int:
        cutoff = (datetime.now() - timedelta(days=max_age_days)).isoformat()
        with self.conn:
            cur = self.conn.execute(
                "DELETE FROM edges WHERE created_at < ?", (cutoff,)
            )
            return cur.rowcount

    def stats(self) -> dict:
        node_count = self.conn.execute("SELECT COUNT(*) FROM nodes").fetchone()[0]
        edge_count = self.conn.execute("SELECT COUNT(*) FROM edges").fetchone()[0]
        types = [
            dict(r)
            for r in self.conn.execute(
                "SELECT entity_type, COUNT(*) as count FROM nodes GROUP BY entity_type"
            ).fetchall()
        ]
        relations = [
            dict(r)
            for r in self.conn.execute(
                "SELECT relation, COUNT(*) as count FROM edges GROUP BY relation"
            ).fetchall()
        ]
        return {
            "node_count": node_count,
            "edge_count": edge_count,
            "types": types,
            "relations": relations,
        }

    # === Reputation methods (for ConsensusValidator) ===

    def get_reputation(self, agent_id: str) -> float:
        """Get agent's reputation score 0.0-1.0."""
        row = self.conn.execute(
            "SELECT metadata FROM nodes WHERE entity_type = 'agent' AND name = ?",
            (agent_id,),
        ).fetchone()
        if row and row["metadata"]:
            meta = json.loads(row["metadata"])
            return meta.get("reputation", 0.5)
        return 0.5

    def set_reputation(self, agent_id: str, score: float) -> None:
        """Set agent's reputation score (clamped 0.0-1.0)."""
        score = max(0.0, min(1.0, score))
        # Ensure agent node exists
        self.add_node("agent", agent_id, {"reputation": score})

    def update_reputation(self, agent_id: str, delta: float, reason: str = "") -> float:
        """Update reputation by delta. Returns new score."""
        current = self.get_reputation(agent_id)
        new_score = max(0.0, min(1.0, current + delta))
        self.add_node("agent", agent_id, {
            "reputation": new_score,
            "last_delta": delta,
            "last_reason": reason,
        })
        return new_score
