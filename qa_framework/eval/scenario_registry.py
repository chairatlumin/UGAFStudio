"""Scenario registry for reproducible agent evaluation."""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path

DEFAULT_DB_PATH = Path.home() / ".ugafstudio" / "eval.db"


class ScenarioRegistry:
    """Manages versioned evaluation scenarios for game QA agents."""

    def __init__(self, db_path: str | None = None) -> None:
        self.db_path = str(db_path) if db_path else str(DEFAULT_DB_PATH)
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _init_db(self) -> None:
        with self._lock:
            conn = self._connect()
            conn.execute("""
                CREATE TABLE IF NOT EXISTS scenarios (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    game_id TEXT NOT NULL,
                    level TEXT NOT NULL,
                    seed INTEGER NOT NULL,
                    expected_behavior TEXT NOT NULL,
                    failure_conditions_json TEXT NOT NULL,
                    version INTEGER DEFAULT 1,
                    created_at REAL NOT NULL,
                    UNIQUE(game_id, level, seed, version)
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_scenarios_game ON scenarios(game_id)")
            conn.commit()
            conn.close()

    def register(
        self,
        game_id: str,
        level: str,
        seed: int,
        expected_behavior: str,
        failure_conditions: list[str],
        version: int = 1,
    ) -> int:
        """Register a new scenario. Returns the scenario ID."""
        with self._lock:
            conn = self._connect()
            cursor = conn.execute(
                """INSERT INTO scenarios (game_id, level, seed, expected_behavior, failure_conditions_json, version, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (game_id, level, seed, expected_behavior, json.dumps(failure_conditions), version, time.time()),
            )
            conn.commit()
            scenario_id = cursor.lastrowid or 0
            conn.close()
            return scenario_id

    def get(self, scenario_id: int) -> dict:
        """Retrieve a scenario by ID."""
        conn = self._connect()
        row = conn.execute("SELECT * FROM scenarios WHERE id = ?", (scenario_id,)).fetchone()
        conn.close()
        if row is None:
            raise KeyError(f"Scenario {scenario_id} not found")
        return {
            "id": row["id"],
            "game_id": row["game_id"],
            "level": row["level"],
            "seed": row["seed"],
            "expected_behavior": row["expected_behavior"],
            "failure_conditions": json.loads(row["failure_conditions_json"]),
            "version": row["version"],
            "created_at": row["created_at"],
        }

    def list_scenarios(self, game_id: str | None = None) -> list[dict]:
        """List all scenarios, optionally filtered by game."""
        conn = self._connect()
        if game_id:
            rows = conn.execute("SELECT * FROM scenarios WHERE game_id = ? ORDER BY id", (game_id,)).fetchall()
        else:
            rows = conn.execute("SELECT * FROM scenarios ORDER BY id").fetchall()
        conn.close()
        return [
            {
                "id": r["id"],
                "game_id": r["game_id"],
                "level": r["level"],
                "seed": r["seed"],
                "expected_behavior": r["expected_behavior"],
                "failure_conditions": json.loads(r["failure_conditions_json"]),
                "version": r["version"],
                "created_at": r["created_at"],
            }
            for r in rows
        ]

    def delete(self, scenario_id: int) -> bool:
        """Delete a scenario by ID."""
        with self._lock:
            conn = self._connect()
            cursor = conn.execute("DELETE FROM scenarios WHERE id = ?", (scenario_id,))
            conn.commit()
            deleted = cursor.rowcount > 0
            conn.close()
            return deleted

    def close(self) -> None:
        """Close all database connections."""
        pass  # Connections are opened/closed per-method
