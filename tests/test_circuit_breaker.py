import time

from qa_framework.secure_observe.circuit_breaker import CircuitBreaker, CircuitState


def test_circuit_starts_closed():
    cb = CircuitBreaker(failure_threshold=3)
    assert cb.state == CircuitState.CLOSED
    assert cb.can_execute("agent-1")


def test_circuit_opens_after_threshold():
    cb = CircuitBreaker(failure_threshold=2)
    cb.record_failure("agent-1")
    cb.record_failure("agent-1")
    assert cb.state == CircuitState.OPEN
    assert not cb.can_execute("agent-1")


def test_circuit_half_open_after_recovery():
    cb = CircuitBreaker(failure_threshold=1, recovery_timeout_s=0)
    cb.record_failure("agent-1")
    assert cb.state == CircuitState.OPEN
    time.sleep(0.05)
    assert cb.can_execute("agent-1")
    assert cb.state == CircuitState.HALF_OPEN


def test_circuit_closes_on_success():
    cb = CircuitBreaker(failure_threshold=1, recovery_timeout_s=0)
    cb.record_failure("agent-1")
    time.sleep(0.05)
    cb.can_execute("agent-1")
    cb.record_success("agent-1")
    assert cb.state == CircuitState.CLOSED


def test_circuit_half_open_failure_reopens():
    cb = CircuitBreaker(failure_threshold=1, recovery_timeout_s=0)
    cb.record_failure("agent-1")
    time.sleep(0.05)
    cb.can_execute("agent-1")  # enters half-open
    cb.record_failure("agent-1")  # fails again
    assert cb.state == CircuitState.OPEN


def test_get_agent_status():
    cb = CircuitBreaker(failure_threshold=2)
    cb.record_failure("agent-1")
    status = cb.get_agent_status("agent-1")
    assert status['agent_id'] == "agent-1"
    assert status['failure_count'] == 1
    assert status['state'] == "closed"


def test_get_all_statuses():
    cb = CircuitBreaker(failure_threshold=3)
    cb.record_failure("agent-1")
    cb.record_failure("agent-2")
    statuses = cb.get_all_statuses()
    assert len(statuses) == 2


def test_dependent_agents_independent():
    cb = CircuitBreaker(failure_threshold=1)
    cb.record_failure("agent-1")
    assert cb.state == CircuitState.OPEN
    assert cb.can_execute("agent-2")  # agent-2 still works


def test_new_agent_auto_closed():
    cb = CircuitBreaker(failure_threshold=3)
    status = cb.get_agent_status("unknown-agent")
    assert status['state'] == "closed"
    assert status['failure_count'] == 0
