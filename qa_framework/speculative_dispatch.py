from __future__ import annotations

import subprocess
import threading
import time
from dataclasses import dataclass, field
from typing import Any

OPENCODE_URL = "http://127.0.0.1:4096"


@dataclass
class Prediction:
    """A predicted next action with confidence score."""

    action: str
    confidence: float
    context: dict[str, Any] = field(default_factory=dict)


class PredictionEngine:
    """Predicts next tool/agent call based on action history."""

    def __init__(self, history: list[str] | None = None) -> None:
        self._history: list[str] = history or []
        self._patterns: dict[tuple[str, ...], dict[str, float]] = {}

    def record(self, action: str) -> None:
        self._history.append(action)

    def learn_pattern(self, prev: list[str], next_action: str) -> None:
        key = tuple(prev[-3:])
        if key not in self._patterns:
            self._patterns[key] = {}
        self._patterns[key][next_action] = self._patterns[key].get(next_action, 0) + 1.0

    def predict_next(self) -> Prediction | None:
        if len(self._history) < 2:
            return None
        key = tuple(self._history[-3:])
        candidates = self._patterns.get(key, {})
        if not candidates:
            return None
        total = sum(candidates.values())
        best_action = max(candidates, key=lambda k: candidates[k])
        return Prediction(
            action=best_action,
            confidence=candidates[best_action] / total,
        )


@dataclass
class SpeculationBudget:
    """Limits concurrent speculative dispatches."""

    max_concurrent: int = 2
    max_runtime_seconds: float = 300.0
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)
    _active: dict[str, float] = field(default_factory=dict, repr=False)

    def can_speculate(self) -> bool:
        with self._lock:
            self._evict_expired()
            return len(self._active) < self.max_concurrent

    def acquire(self, task_id: str) -> bool:
        with self._lock:
            self._evict_expired()
            if len(self._active) >= self.max_concurrent:
                return False
            self._active[task_id] = time.monotonic()
            return True

    def release(self, task_id: str) -> None:
        with self._lock:
            self._active.pop(task_id, None)

    def _evict_expired(self) -> None:
        now = time.monotonic()
        expired = [tid for tid, ts in self._active.items() if now - ts > self.max_runtime_seconds]
        for tid in expired:
            del self._active[tid]


class SpeculativeDispatcher:
    """Pre-dispatches OpenCode subagents based on prediction; kills if wrong."""

    def __init__(
        self,
        budget: SpeculationBudget | None = None,
        engine: PredictionEngine | None = None,
    ) -> None:
        self.budget = budget or SpeculationBudget()
        self.engine = engine or PredictionEngine()
        self._processes: dict[str, subprocess.Popen] = {}
        self._lock = threading.Lock()

    def record_action(self, action: str) -> None:
        self.engine.record(action)

    def speculate(self, target: str, prompt: str = "", threshold: float = 0.6) -> bool:
        """Pre-dispatch if prediction confidence >= threshold and budget allows."""
        pred = self.engine.predict_next()
        if pred is None or pred.confidence < threshold:
            return False
        if not self.budget.can_speculate():
            return False
        if not self.budget.acquire(target):
            return False
        try:
            proc = subprocess.Popen(
                ["opencode", "run", "--model", "opencode/nemotron-3.5-lightning-free", prompt],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            with self._lock:
                self._processes[target] = proc
            return True
        except Exception:
            self.budget.release(target)
            return False

    def is_alive(self, target: str) -> bool:
        with self._lock:
            proc = self._processes.get(target)
            if proc is None:
                return False
            return proc.poll() is None

    def kill(self, target: str) -> bool:
        with self._lock:
            proc = self._processes.pop(target, None)
            if proc is None:
                return False
        try:
            proc.kill()
            proc.wait(timeout=5)
        except Exception:
            pass
        self.budget.release(target)
        return True

    def complete(self, target: str, was_correct: bool) -> None:
        """Mark speculation as correctly predicted (keep) or wrong (kill)."""
        if was_correct:
            # Keep process running — the caller will consume output
            self.budget.release(target)
        else:
            self.kill(target)
