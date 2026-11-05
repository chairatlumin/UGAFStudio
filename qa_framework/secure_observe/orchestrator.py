import time
from dataclasses import dataclass, field
from typing import Any, Optional

from .circuit_breaker import CircuitBreaker
from .sandbox import DispatchResult, SandboxedDispatch
from .telemetry import AgentTelemetry
from .trust_boundary import validate_a2a_message
from .verification_gate import GateResult, VerificationGate


@dataclass
class ObserveResult:
    task_id: str
    agent_id: str
    success: bool
    dispatch_result: Optional[DispatchResult] = None
    gate_result: Optional[GateResult] = None
    circuit_open: bool = False
    validation_error: Optional[str] = None
    error: Optional[str] = None
    total_duration_ms: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


class SecureObserve:
    def __init__(
        self,
        workspace: str = ".",
        python_path: str = "python",
        telemetry_path: str = ".ai/telemetry/traces.jsonl",
        failure_threshold: int = 3,
        dispatch_timeout_s: int = 300,
        memory_limit_mb: int = 512,
    ):
        self.workspace = workspace
        self.dispatch = SandboxedDispatch(
            workspace=workspace,
            timeout_s=dispatch_timeout_s,
            memory_limit_mb=memory_limit_mb,
        )
        self.gate = VerificationGate(
            workspace=workspace,
            python_path=python_path,
        )
        self.telemetry = AgentTelemetry(output_path=telemetry_path)
        self.circuit_breaker = CircuitBreaker(failure_threshold=failure_threshold)

    def run_task(
        self,
        task_id: str,
        agent_id: str,
        command: str,
        files_to_verify: Optional[list[str]] = None,
    ) -> ObserveResult:
        start = time.monotonic()

        # Phase 1: Trust boundary validation
        try:
            validate_a2a_message({"command": command, "agent_id": agent_id})
            self.telemetry.record(task_id, agent_id, "validation", 0, True)
        except ValueError as e:
            self.telemetry.record(task_id, agent_id, "validation", 0, False, {"error": str(e)})
            return ObserveResult(
                task_id=task_id,
                agent_id=agent_id,
                success=False,
                validation_error=str(e),
                error=f"Validation failed: {e}",
            )

        # Phase 2: Circuit breaker check
        if not self.circuit_breaker.can_execute(agent_id):
            self.telemetry.record(task_id, agent_id, "circuit_breaker", 0, False)
            return ObserveResult(
                task_id=task_id,
                agent_id=agent_id,
                success=False,
                circuit_open=True,
                error="Circuit breaker OPEN — agent quarantined",
            )

        self.telemetry.record(task_id, agent_id, "circuit_breaker", 0, True)

        # Phase 3: Sandboxed execution
        dispatch_start = time.monotonic()
        dispatch_result = self.dispatch.run(command, task_id=task_id)
        dispatch_duration = (time.monotonic() - dispatch_start) * 1000
        self.telemetry.record(
            task_id, agent_id, "execution", dispatch_duration,
            dispatch_result.success,
            {"timed_out": dispatch_result.timed_out, "killed": dispatch_result.killed},
        )

        if not dispatch_result.success:
            self.circuit_breaker.record_failure(agent_id)
            total_duration = (time.monotonic() - start) * 1000
            self.telemetry.record(task_id, agent_id, "completion", total_duration, False)
            return ObserveResult(
                task_id=task_id,
                agent_id=agent_id,
                success=False,
                dispatch_result=dispatch_result,
                error=f"Dispatch failed: {dispatch_result.stderr[:200]}",
            )

        # Phase 4: Verification gate
        gate_start = time.monotonic()
        changed_files = files_to_verify or []
        gate_result = self.gate.verify(changed_files)
        gate_duration = (time.monotonic() - gate_start) * 1000
        gate_details = {
            "ruff": gate_result.ruff_pass,
            "mypy": gate_result.mypy_pass,
            "pytest": gate_result.pytest_pass,
        }
        self.telemetry.record(
            task_id, agent_id, "verification", gate_duration,
            gate_result.all_pass, gate_details,
        )

        if not gate_result.all_pass:
            self.circuit_breaker.record_failure(agent_id)
            total_duration = (time.monotonic() - start) * 1000
            self.telemetry.record(task_id, agent_id, "completion", total_duration, False)
            return ObserveResult(
                task_id=task_id,
                agent_id=agent_id,
                success=False,
                dispatch_result=dispatch_result,
                gate_result=gate_result,
                error=f"Verification failed: {gate_result.details}",
            )

        # Phase 5: Success
        self.circuit_breaker.record_success(agent_id)
        total_duration = (time.monotonic() - start) * 1000
        self.telemetry.record(task_id, agent_id, "completion", total_duration, True)
        self.telemetry.flush()

        return ObserveResult(
            task_id=task_id,
            agent_id=agent_id,
            success=True,
            dispatch_result=dispatch_result,
            gate_result=gate_result,
            total_duration_ms=total_duration,
        )
