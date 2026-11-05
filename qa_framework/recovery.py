"""Self-healing recovery primitives for UGAFStudio QA runs."""

from __future__ import annotations

import enum
import subprocess
import time
from dataclasses import dataclass, field
from typing import Callable

import psutil


class RecoveryAction(enum.Enum):
    """Recovery actions in order of escalation."""
    RETRY = "retry"
    RELAUNCH = "relaunch"
    STATE_RESET = "state_reset"
    FALLBACK_INPUT = "fallback_input"
    ESCALATE = "escalate"


@dataclass
class RecoveryResult:
    """Result of a recovery attempt."""
    action: RecoveryAction
    success: bool
    elapsed: float = 0.0
    context: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "action": self.action.value,
            "success": self.success,
            "elapsed": self.elapsed,
            "context": self.context,
        }


@dataclass
class RecoveryManager:
    """Manages self-healing recovery for QA runs.
    
    Applies the 5 recovery primitives in order:
    Retry (up to max_retries) → Relaunch → State reset → Fallback input → Escalate
    """
    max_retries: int = 3
    retry_delay: float = 5.0
    max_relaunches: int = 2
    _retry_count: int = 0
    _relaunch_count: int = 0
    _log: list[RecoveryResult] = field(default_factory=list)

    def reset(self) -> None:
        """Reset counters for a new recovery sequence."""
        self._retry_count = 0
        self._relaunch_count = 0

    @property
    def log(self) -> list[dict]:
        return [r.to_dict() for r in self._log]

    def is_recoverable(self, error: Exception) -> bool:
        """Check if an error is recoverable."""
        recoverable_types = (
            subprocess.TimeoutExpired,
            ProcessLookupError,
            ConnectionError,
            OSError,
        )
        return isinstance(error, recoverable_types)

    def recover(
        self,
        error: Exception,
        *,
        relaunch_fn: Callable[[], bool] | None = None,
        state_reset_fn: Callable[[], bool] | None = None,
        fallback_input_fn: Callable[[], bool] | None = None,
    ) -> RecoveryResult:
        """Attempt recovery from a failure."""
        start = time.monotonic()

        if not self.is_recoverable(error):
            result = RecoveryResult(
                action=RecoveryAction.ESCALATE,
                success=False,
                context={"reason": f"Unrecoverable error: {type(error).__name__}: {error}"},
            )
            self._log.append(result)
            result.elapsed = time.monotonic() - start
            return result

        # 1. Retry
        if self._retry_count < self.max_retries:
            self._retry_count += 1
            time.sleep(self.retry_delay)
            result = RecoveryResult(
                action=RecoveryAction.RETRY,
                success=True,
                context={"attempt": self._retry_count, "max": self.max_retries},
            )
            self._log.append(result)
            result.elapsed = time.monotonic() - start
            return result

        # 2. Relaunch
        if self._relaunch_count < self.max_relaunches and relaunch_fn is not None:
            self._relaunch_count += 1
            try:
                success = relaunch_fn()
            except Exception:
                success = False
            result = RecoveryResult(
                action=RecoveryAction.RELAUNCH,
                success=success,
                context={"attempt": self._relaunch_count, "max": self.max_relaunches},
            )
            self._log.append(result)
            result.elapsed = time.monotonic() - start
            if success:
                self._retry_count = 0
            return result

        # 3. State reset
        if state_reset_fn is not None:
            try:
                success = state_reset_fn()
            except Exception:
                success = False
            result = RecoveryResult(
                action=RecoveryAction.STATE_RESET,
                success=success,
                context={},
            )
            self._log.append(result)
            result.elapsed = time.monotonic() - start
            if success:
                self._retry_count = 0
            return result

        # 4. Fallback input
        if fallback_input_fn is not None:
            try:
                success = fallback_input_fn()
            except Exception:
                success = False
            result = RecoveryResult(
                action=RecoveryAction.FALLBACK_INPUT,
                success=success,
                context={},
            )
            self._log.append(result)
            result.elapsed = time.monotonic() - start
            if success:
                self._retry_count = 0
            return result

        # 5. Escalation
        result = RecoveryResult(
            action=RecoveryAction.ESCALATE,
            success=False,
            context={
                "reason": "All recovery primitives exhausted",
                "retries": self._retry_count,
                "relaunches": self._relaunch_count,
            },
        )
        self._log.append(result)
        result.elapsed = time.monotonic() - start
        return result

    def kill_process(self, pid: int) -> bool:
        """Kill a process by PID."""
        try:
            proc = psutil.Process(pid)
            proc.kill()
            proc.wait(timeout=10)
            return True
        except (psutil.NoSuchProcess, psutil.TimeoutExpired):
            return False

    def launch_process(self, cmd: list[str], cwd: str | None = None) -> subprocess.Popen:
        """Launch a new process."""
        return subprocess.Popen(
            cmd,
            cwd=cwd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if hasattr(subprocess, 'CREATE_NEW_PROCESS_GROUP') else 0,
        )
