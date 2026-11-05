"""Tests for CircuitBreaker (qa_framework root version)."""
from __future__ import annotations

from qa_framework.circuit_breaker import CircuitBreaker


class TestCircuitBreakerRoot:
    def test_circuit_trips_after_three_failures(self):
        cb = CircuitBreaker(failure_threshold=3, cooldown=300)
        assert not cb.is_tripped("agent_x")
        cb.record_failure("agent_x")
        cb.record_failure("agent_x")
        assert not cb.is_tripped("agent_x")
        cb.record_failure("agent_x")
        assert cb.is_tripped("agent_x")

    def test_success_resets_counter(self):
        cb = CircuitBreaker(failure_threshold=3, cooldown=300)
        cb.record_failure("agent_x")
        cb.record_failure("agent_x")
        cb.record_success("agent_x")
        assert not cb.is_tripped("agent_x")
        cb.record_failure("agent_x")
        assert not cb.is_tripped("agent_x")



    def test_get_status(self):
        cb = CircuitBreaker(failure_threshold=3, cooldown=300)
        status = cb.get_status("unknown")
        assert status["tripped"] is False
        assert status["failures"] == 0

        cb.record_failure("a")
        status = cb.get_status("a")
        assert status["failures"] == 1
        assert status["tripped"] is False
