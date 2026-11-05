"""Observability primitives for UGAFStudio QA — tracing, circuit breakers, idempotency.

Per 2026 production agent reliability patterns:
- TraceSpan: structured timing + outcome for every QA operation
- CircuitBreaker: stop retrying after N consecutive failures (frame_diff/state_ocr)
- IdempotencyGuard: prevent duplicate game launches
- TraceExporter: JSONL export compatible with OTLP visualization tools
"""
from __future__ import annotations

import json
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Generator

# ---------------------------------------------------------------------------
# TraceSpan — structured timing + outcome
# ---------------------------------------------------------------------------

@dataclass
class TraceSpan:
    """Structured trace span for a QA operation (context-manager based).

    Example::

        with TraceSpan("launch_game", metadata={"app_id": 4077460}) as span:
            proc = launch(...)
        # span.elapsed, span.success, span.error populated automatically
    """
    name: str
    start_time: float = 0.0
    end_time: float = 0.0
    elapsed: float = 0.0
    success: bool = False
    error: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def __enter__(self) -> TraceSpan:
        self.start_time = time.monotonic()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.end_time = time.monotonic()
        self.elapsed = self.end_time - self.start_time
        self.success = exc_type is None
        if exc_val:
            self.error = str(exc_val)
        return False  # do not suppress exceptions

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "elapsed_ms": round(self.elapsed * 1000, 2),
            "success": self.success,
            "error": self.error,
            "metadata": self.metadata,
        }


# ---------------------------------------------------------------------------
# CircuitBreaker — stop retrying after N consecutive failures
# ---------------------------------------------------------------------------

@dataclass
class CircuitBreaker:
    """Circuit breaker for verification steps — stops after N consecutive failures.

    Use with ``frame_diff`` / ``state_ocr`` to prevent infinite retry loops
    when the game is stuck on a black screen.

    Example::

        cb = CircuitBreaker(max_failures=5)
        while not done:
            if cb.is_open:
                break  # stop retrying
            if frame_diff(prev, curr):
                cb.record_success()
                done = True
            else:
                cb.record_failure()
    """
    max_failures: int = 5
    failure_count: int = 0
    success_count: int = 0
    _lock: threading.Lock = field(default_factory=threading.Lock)

    @property
    def is_open(self) -> bool:
        return self.failure_count >= self.max_failures

    def record_failure(self) -> None:
        with self._lock:
            self.failure_count += 1

    def record_success(self) -> None:
        with self._lock:
            self.success_count += 1
            self.failure_count = 0

    def reset(self) -> None:
        with self._lock:
            self.failure_count = 0
            self.success_count = 0


# ---------------------------------------------------------------------------
# IdempotencyGuard — prevent duplicate game launches
# ---------------------------------------------------------------------------

@dataclass
class IdempotencyGuard:
    """Prevents duplicate operations (e.g., double game launch) using idempotency keys.

    Example::

        guard = IdempotencyGuard()
        if guard.acquire("launch_shinebringer"):
            try:
                launch_game(...)
            finally:
                guard.release("launch_shinebringer")
    """
    _active: set[str] = field(default_factory=set)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def acquire(self, key: str) -> bool:
        with self._lock:
            if key in self._active:
                return False
            self._active.add(key)
            return True

    def release(self, key: str) -> None:
        with self._lock:
            self._active.discard(key)

    @property
    def active_count(self) -> int:
        with self._lock:
            return len(self._active)


# ---------------------------------------------------------------------------
# TraceExporter — JSONL export for OTLP-compatible visualization
# ---------------------------------------------------------------------------

class TraceExporter:
    """Exports trace spans as JSONL (OTLP-compatible format).

    Each span is one JSON object per line, suitable for ingestion by
    Grafana Loki, Datadog, or any OTLP-aware trace viewer.
    """
    def __init__(self, output_path: str) -> None:
        self.output_path = output_path

    def export(self, spans: list[TraceSpan]) -> None:
        with open(self.output_path, "w", encoding="utf-8") as f:
            for span in spans:
                f.write(json.dumps(span.to_dict()) + "\n")


# ---------------------------------------------------------------------------
# Module-level singletons (convenience)
# ---------------------------------------------------------------------------

_default_guard = IdempotencyGuard()
_default_breaker = CircuitBreaker()


def default_idempotency_guard() -> IdempotencyGuard:
    return _default_guard


def default_circuit_breaker() -> CircuitBreaker:
    return _default_breaker


@contextmanager
def traced(name: str, **metadata: Any) -> Generator[TraceSpan, None, None]:
    """Convenience context manager — yields a TraceSpan, then discards it.

    Use when you don't need to retain the span object afterwards.
    """
    span = TraceSpan(name=name, metadata=metadata)
    with span:
        yield span
