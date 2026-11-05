import threading
import time
from enum import Enum
from typing import Dict


class CircuitState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    def __init__(
        self,
        failure_threshold: int = 3,
        recovery_timeout_s: float = 300.0,
    ):
        self.failure_threshold = failure_threshold
        self.recovery_timeout_s = recovery_timeout_s
        self._agent_state: Dict[str, CircuitState] = {}
        self._agent_failures: Dict[str, int] = {}
        self._agent_last_failure: Dict[str, float] = {}
        self._lock = threading.RLock()

    @property
    def state(self) -> CircuitState:
        with self._lock:
            states = list(self._agent_state.values())
            if CircuitState.OPEN in states:
                return CircuitState.OPEN
            if CircuitState.HALF_OPEN in states:
                return CircuitState.HALF_OPEN
            return CircuitState.CLOSED

    def can_execute(self, agent_id: str) -> bool:
        with self._lock:
            state = self._agent_state.get(agent_id, CircuitState.CLOSED)

            if state == CircuitState.CLOSED:
                return True

            if state == CircuitState.OPEN:
                last_failure = self._agent_last_failure.get(agent_id, 0)
                if time.time() - last_failure >= self.recovery_timeout_s:
                    self._agent_state[agent_id] = CircuitState.HALF_OPEN
                    return True
                return False

            if state == CircuitState.HALF_OPEN:
                return True

            return True

    def record_success(self, agent_id: str) -> None:
        with self._lock:
            self._agent_state[agent_id] = CircuitState.CLOSED
            self._agent_failures[agent_id] = 0

    def record_failure(self, agent_id: str) -> None:
        with self._lock:
            current = self._agent_failures.get(agent_id, 0) + 1
            self._agent_failures[agent_id] = current
            self._agent_last_failure[agent_id] = time.time()
            self._agent_state[agent_id] = self._agent_state.get(agent_id, CircuitState.CLOSED)

            if current >= self.failure_threshold:
                self._agent_state[agent_id] = CircuitState.OPEN
            elif self._agent_state.get(agent_id) == CircuitState.HALF_OPEN:
                self._agent_state[agent_id] = CircuitState.OPEN

    def get_agent_status(self, agent_id: str) -> dict:
        with self._lock:
            return {
                "agent_id": agent_id,
                "state": self._agent_state.get(agent_id, CircuitState.CLOSED).value,
                "failure_count": self._agent_failures.get(agent_id, 0),
                "last_failure": self._agent_last_failure.get(agent_id, 0),
            }

    def get_all_statuses(self) -> list[dict]:
        with self._lock:
            return [self.get_agent_status(aid) for aid in self._agent_state]
