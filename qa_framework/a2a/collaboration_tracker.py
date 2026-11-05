"""Collaboration tracker for A2A orchestration."""
import sqlite3
import uuid
from typing import List, Optional
from datetime import datetime
from .collaboration_prior import CollaborationPrior, CollaborationResult


class CollaborationTracker:
    def __init__(self, db_path: str = "collaboration_priors.db"):
        self._uri = db_path == ":memory:"
        self.db_path = (
            f"file:collaboration_tracker_{uuid.uuid4().hex}?mode=memory&cache=shared"
            if self._uri else db_path
        )
        self._keeper = sqlite3.connect(self.db_path, uri=True) if self._uri else None
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path, uri=self._uri) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS collaboration_priors (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_type TEXT,
                    source_agent TEXT,
                    target_agent TEXT,
                    success_count INTEGER DEFAULT 0,
                    failure_count INTEGER DEFAULT 0,
                    avg_execution_time REAL DEFAULT 0.0,
                    last_used TIMESTAMP
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS collaboration_results (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT,
                    source_agent TEXT,
                    target_agent TEXT,
                    success BOOLEAN,
                    execution_time REAL,
                    timestamp TIMESTAMP,
                    error_message TEXT
                )
            """)

    def record(self, result: CollaborationResult):
        with sqlite3.connect(self.db_path, uri=self._uri) as conn:
            conn.execute("""
                INSERT INTO collaboration_results
                (task_id, source_agent, target_agent, success, execution_time, timestamp, error_message)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (result.task_id, result.source_agent, result.target_agent,
                  result.success, result.execution_time, result.timestamp, result.error_message))

            cursor = conn.execute("""
                SELECT id, success_count, failure_count, avg_execution_time
                FROM collaboration_priors
                WHERE source_agent = ? AND target_agent = ?
            """, (result.source_agent, result.target_agent))
            row = cursor.fetchone()

            if row:
                prior_id, success_count, failure_count, avg_time = row
                if result.success:
                    success_count += 1
                else:
                    failure_count += 1
                total = success_count + failure_count
                new_avg = (avg_time * (total - 1) + result.execution_time) / total
                conn.execute("""
                    UPDATE collaboration_priors
                    SET success_count = ?, failure_count = ?, avg_execution_time = ?, last_used = ?
                    WHERE id = ?
                """, (success_count, failure_count, new_avg, result.timestamp, prior_id))
            else:
                conn.execute("""
                    INSERT INTO collaboration_priors
                    (task_type, source_agent, target_agent, success_count, failure_count, avg_execution_time, last_used)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, ("default", result.source_agent, result.target_agent,
                      1 if result.success else 0, 0 if result.success else 1,
                      result.execution_time, result.timestamp))

    def get_priors(self, source_agent: str, target_agent: str) -> List[CollaborationPrior]:
        with sqlite3.connect(self.db_path, uri=self._uri) as conn:
            cursor = conn.execute("""
                SELECT task_type, source_agent, target_agent, success_count, failure_count, avg_execution_time, last_used
                FROM collaboration_priors
                WHERE source_agent = ? AND target_agent = ?
            """, (source_agent, target_agent))
            rows = cursor.fetchall()
            return [CollaborationPrior(
                task_type=row[0],
                source_agent=row[1],
                target_agent=row[2],
                success_count=row[3],
                failure_count=row[4],
                avg_execution_time=row[5],
                last_used=row[6]
            ) for row in rows]

    def suggest_best_agent(self, source_agent: str, candidates: List[str]) -> Optional[str]:
        best_agent = None
        best_rate = -1.0
        for candidate in candidates:
            priors = self.get_priors(source_agent, candidate)
            if priors:
                rate = priors[0].success_rate
                if rate > best_rate:
                    best_rate = rate
                    best_agent = candidate
        return best_agent
