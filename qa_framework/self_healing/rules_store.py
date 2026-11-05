"""Accumulated behavioral rules store with confidence scoring."""

import sqlite3
import time
from typing import Dict, List, Optional

SCHEMA_CREATE = """CREATE TABLE IF NOT EXISTS rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pattern TEXT NOT NULL UNIQUE,
    action TEXT NOT NULL,
    source TEXT DEFAULT 'auto',
    confidence REAL DEFAULT 0.5,
    created_at REAL NOT NULL,
    last_fired REAL,
    fire_count INTEGER DEFAULT 0
)"""

SCHEMA_INDEXES = """CREATE INDEX IF NOT EXISTS idx_pattern ON rules(pattern);
CREATE INDEX IF NOT EXISTS idx_confidence ON rules(confidence);"""


class RulesStore:
    def __init__(self, db_path: str = "self_healing_rules.db") -> None:
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA_CREATE)
        self.conn.executescript(SCHEMA_INDEXES)
        self.conn.commit()

    def add_rule(
        self,
        pattern: str,
        action: str,
        source: str = "auto",
        confidence: float = 0.5,
    ) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO rules "
            "(pattern, action, source, confidence, created_at) VALUES (?, ?, ?, ?, ?)",
            (pattern, action, source, confidence, time.time()),
        )
        self.conn.commit()

    def find_matching_rules(
        self, context: Dict[str, object], min_confidence: float = 0.3
    ) -> List[Dict[str, object]]:
        """Find rules whose pattern matches a key in context."""
        rows = self.conn.execute(
            "SELECT * FROM rules WHERE confidence >= ? ORDER BY confidence DESC",
            (min_confidence,),
        ).fetchall()
        results: List[Dict[str, object]] = []
        for row in rows:
            pattern = row["pattern"]
            error_type = context.get("error_type", "")
            if pattern in str(error_type):
                results.append(dict(row))
        return results

    def fire_rule(self, rule_id: int) -> None:
        self.conn.execute(
            "UPDATE rules SET last_fired = ?, fire_count = fire_count + 1, "
            "confidence = MIN(1.0, confidence + 0.05) WHERE id = ?",
            (time.time(), rule_id),
        )
        self.conn.commit()

    def record_outcome(self, rule_id: int, success: bool) -> None:
        delta = 0.05 if success else -0.15
        self.conn.execute(
            "UPDATE rules SET confidence = MAX(0.0, MIN(1.0, confidence + ?)) WHERE id = ?",
            (delta, rule_id),
        )
        self.conn.commit()

    def prune_stale(self, max_age_days: int = 30, min_confidence: float = 0.2) -> None:
        cutoff = time.time() - (max_age_days * 86400)
        self.conn.execute(
            "DELETE FROM rules WHERE created_at < ? AND confidence < ?",
            (cutoff, min_confidence),
        )
        self.conn.commit()

    def get_rule(self, rule_id: int) -> Optional[Dict[str, object]]:
        row = self.conn.execute("SELECT * FROM rules WHERE id = ?", (rule_id,)).fetchone()
        return dict(row) if row else None

    def count_rules(self) -> int:
        return int(self.conn.execute("SELECT COUNT(*) FROM rules").fetchone()[0])

    def get_all_rules(self) -> List[Dict[str, object]]:
        rows = self.conn.execute("SELECT * FROM rules ORDER BY confidence DESC").fetchall()
        return [dict(r) for r in rows]
