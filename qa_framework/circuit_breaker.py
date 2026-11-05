from __future__ import annotations

import time


class CircuitBreaker:
    """Track agent failures and trip after threshold.

    Trip after ``failure_threshold`` consecutive failures.
    Auto-reset after ``cooldown`` seconds.
    ``record_success`` resets the counter immediately.
    """

    def __init__(self, failure_threshold: int = 3, cooldown: float = 300.0) -> None:
        self.failure_threshold = failure_threshold
        self.cooldown = cooldown
        self._failures: dict[str, int] = {}
        self._last_failure: dict[str, float] = {}

    # ── public API ──────────────────────────────────────────────────────

    def is_tripped(self, agent_id: str) -> bool:
        """Return True if the circuit is tripped for *agent_id*."""
        failures = self._failures.get(agent_id, 0)
        if failures < self.failure_threshold:
            return False
        # Check if cooldown has elapsed (auto-reset)
        last = self._last_failure.get(agent_id, 0.0)
        return time.time() - last < self.cooldown

    def record_failure(self, agent_id: str) -> None:
        """Record a failure for *agent_id*.

        Trip the circuit if *failure_threshold* consecutive failures
        are reached.
        """
        current = self._failures.get(agent_id, 0) + 1
        self._failures[agent_id] = current
        self._last_failure[agent_id] = time.time()

    def record_success(self, agent_id: str) -> None:
        """Reset the failure counter immediately."""
        self._failures[agent_id] = 0
        # cooldown_remaining is computed per get_status; no state needed here

    def get_status(self, agent_id: str) -> dict[str, object]:
        """Return status for *agent_id*.

        Fields: ``tripped``, ``failures``, ``cooldown_remaining``.
        """
        failures = self._failures.get(agent_id, 0)
        tripped = failures >= self.failure_threshold and (
            time.time() - self._last_failure.get(agent_id, 0.0)
        ) < self.cooldown

        last = self._last_failure.get(agent_id, 0.0)
        cooldown_remaining = max(0.0, self.cooldown - (time.time() - last)) if tripped else 0.0

        return {
            "tripped": tripped,
            "failures": failures,
            "cooldown_remaining": round(cooldown_remaining, 2),
        }
