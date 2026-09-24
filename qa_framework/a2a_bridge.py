"""A2A Protocol Bridge for UGAFStudio — standard Agent2Agent protocol support."""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Generator, NamedTuple, Optional

from qa_framework.adversarial_vision import AdversarialVisionGuard
from qa_framework.circuit_breaker import CircuitBreaker
from qa_framework.memory_compactor import MemoryCompactor
from qa_framework.reliability_tracker import DispatchOutcome, ReliabilityTracker
from qa_framework.tool_result_validator import ToolResultValidator
from qa_framework.workspace_locker import WorkspaceLocker

if TYPE_CHECKING:
    from qa_framework.consensus_validator import ConsensusResult
    from qa_framework.intent_scanner import IntentScanner


__all__ = [
    "A2ATaskStatus",
    "A2AMessage",
    "A2AArtifact",
    "A2ATask",
    "A2AEvent",
    "A2AProtocolBridge",
]


class A2ATaskStatus(Enum):
    SUBMITTED = "submitted"
    WORKING = "working"
    INPUT_REQUIRED = "input-required"
    COMPLETED = "completed"
    CANCELED = "canceled"
    FAILED = "failed"


class A2AMessage(NamedTuple):
    role: str
    parts: list[dict]
    metadata: dict


class A2AArtifact(NamedTuple):
    artifact_id: str
    artifact_type: str
    content: str
    metadata: dict


class A2ATask(NamedTuple):
    id: str
    context_id: Optional[str]
    status: A2ATaskStatus
    history: list[A2AMessage]
    artifacts: list[A2AArtifact]
    created_at: str
    error: Optional[str] = None


class A2AEvent(NamedTuple):
    event: str
    task_id: str
    data: dict


class SecurityException(Exception):
    """Raised when agent output is blocked by IntentScanner."""


class A2AProtocolBridge:
    """Bridge between UGAFStudio and A2A protocol v1.0."""

    def __init__(
        self,
        agent_name: str = "ugafstudio-agent",
        version: str = "1.0.0",
        url: str = "http://localhost:4096",
        scanner: "IntentScanner | None" = None,
    ) -> None:
        self.agent_name = agent_name
        self.version = version
        self.url = url
        self._tasks: dict[str, A2ATask] = {}
        self.scanner = scanner
        self._circuit = CircuitBreaker()
        self._locker = WorkspaceLocker()
        self._vision_guard = AdversarialVisionGuard()
        self._reliability = ReliabilityTracker()
        self._result_validator = ToolResultValidator()
        self._memory = MemoryCompactor()

    def agent_card(self) -> dict:
        return {
            "name": "UGAFStudio Agent",
            "description": "Game QA orchestration agent with multi-agent dispatch",
            "version": self.version,
            "url": self.url,
            "capabilities": [
                "task_dispatch",
                "code_generation",
                "qa_verification",
                "test_execution",
            ],
            "authentication": {"type": "none"},
            "skills": [
                {
                    "name": "dispatch_opencode",
                    "description": "Dispatch coding task to OpenCode agent",
                },
                {
                    "name": "run_tests",
                    "description": "Run pytest validation suite",
                },
                {
                    "name": "audit_trail",
                    "description": "Query execution audit logs",
                },
            ],
        }

    def create_task(
        self, input_text: str, context_id: Optional[str] = None
    ) -> A2ATask:
        task_id = str(uuid.uuid4())
        now = datetime.now().isoformat()
        msg = A2AMessage(role="user", parts=[{"type": "text", "text": input_text}], metadata={})
        task = A2ATask(
            id=task_id,
            context_id=context_id,
            status=A2ATaskStatus.SUBMITTED,
            history=[msg],
            artifacts=[],
            created_at=now,
        )
        self._tasks[task_id] = task
        return task

    def get_task(self, task_id: str) -> Optional[A2ATask]:
        return self._tasks.get(task_id)

    def update_task_status(
        self, task_id: str, status: A2ATaskStatus, error: Optional[str] = None
    ) -> A2ATask:
        task = self._tasks[task_id]
        updated = task._replace(status=status, error=error)
        self._tasks[task_id] = updated
        return updated

    def add_message(
        self,
        task_id: str,
        role: str,
        text: str,
        metadata: Optional[dict] = None,
    ) -> A2ATask:
        task = self._tasks[task_id]
        msg = A2AMessage(role=role, parts=[{"type": "text", "text": text}], metadata=metadata or {})
        updated = task._replace(history=[*task.history, msg])
        self._tasks[task_id] = updated
        return updated

    def add_artifact(
        self,
        task_id: str,
        artifact_type: str,
        content: str,
        metadata: Optional[dict] = None,
    ) -> A2ATask:
        task = self._tasks[task_id]
        art = A2AArtifact(
            artifact_id=str(uuid.uuid4()),
            artifact_type=artifact_type,
            content=content,
            metadata=metadata or {},
        )
        updated = task._replace(artifacts=[*task.artifacts, art])
        self._tasks[task_id] = updated
        return updated

    def dispatch_to_opencode(
        self, task_id: str, model: str = "opencode/nemotron-3.5-lightning-free",
        agent_id: str = "opencode",
    ) -> A2ATask:
        task = self._tasks.get(task_id)
        if task is None:
            raise KeyError(f"Task {task_id} not found")

        # Circuit breaker check
        if self._circuit.is_tripped(agent_id):
            msg = (
                f"Circuit tripped for agent '{agent_id}' — dispatch skipped"
            )
            self.add_message(task_id, "system", msg)
            return self.update_task_status(
                task_id, A2ATaskStatus.FAILED,
                error=f"Agent '{agent_id}' circuit tripped (cooldown active)",
            )

        self.update_task_status(task_id, A2ATaskStatus.WORKING)

        try:
            user_input = task.history[0].parts[0].get("text", "") if task.history else ""
            cmd = ["opencode", "run", "--model", model, user_input]
            import subprocess
            import time

            start_time = time.time()
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=600
            )
            duration_ms = int((time.time() - start_time) * 1000)

            # Validate output structure if it looks like JSON
            output = result.stdout
            if output and output.strip().startswith("{"):
                val_result = self._result_validator.validate_json(output)
                if not val_result.is_valid:
                    self.add_message(
                        task_id, "system",
                        f"Output JSON parse warning: {val_result.errors}",
                    )

            # Record reliability outcome
            outcome = DispatchOutcome.SUCCESS if result.returncode == 0 else DispatchOutcome.FAILURE
            self._reliability.record_dispatch(
                agent_id=agent_id,
                task_type="opencode_dispatch",
                model=model,
                outcome=outcome,
                duration_ms=duration_ms,
                confidence=0.8 if result.returncode == 0 else 0.2,
            )

            # IntentScanner: scan agent output before processing
            output = result.stdout
            if self.scanner and output:
                scan_result = self.scanner.scan_agent_output("opencode", output)
                if scan_result.action == "block":
                    self.add_message(
                        task_id, "security",
                        f"Output blocked by IntentScanner: {scan_result.findings}"
                    )
                    return self.update_task_status(
                        task_id, A2ATaskStatus.FAILED,
                        error=f"Security: output blocked (risk={scan_result.risk_score})"
                    )
                elif scan_result.action == "sanitize":
                    # Redact matched spans (reverse order to preserve positions)
                    for finding in sorted(
                        scan_result.findings, key=lambda x: x.position[0], reverse=True
                    ):
                        start = finding.position[0]
                        end = finding.position[1]
                        output = output[:start] + "[REDACTED]" + output[end:]
                    self.add_message(
                        task_id, "security",
                        f"Output sanitized: {len(scan_result.findings)} redactions"
                    )

            if result.returncode == 0:
                self._circuit.record_success(agent_id)
                self.add_artifact(task_id, "log", output)
                self.add_message(task_id, "agent", "Completed with exit code 0")
                return self.update_task_status(task_id, A2ATaskStatus.COMPLETED)
            else:
                self._circuit.record_failure(agent_id)
                self.add_message(task_id, "agent", f"Failed: {result.stderr[:500]}")
                return self.update_task_status(
                    task_id, A2ATaskStatus.FAILED, error=result.stderr[:500]
                )
        except Exception as e:
            self._circuit.record_failure(agent_id)
            self.add_message(task_id, "agent", f"Exception: {e}")
            return self.update_task_status(task_id, A2ATaskStatus.FAILED, error=str(e))

    def stream_task(self, task_id: str) -> Generator[A2AEvent, None, None]:
        task = self._tasks.get(task_id)
        if task is None:
            return
        yield A2AEvent(
            event="status",
            task_id=task_id,
            data={"status": task.status.value, "error": task.error},
        )
        for art in task.artifacts:
            yield A2AEvent(
                event="artifact",
                task_id=task_id,
                data={
                    "artifact_id": art.artifact_id,
                    "type": art.artifact_type,
                    "content": art.content[:200],
                },
            )

    def dispatch_consensus(
        self,
        task: A2ATask,
        agent_ids: list[str],
        min_confidence: float = 0.7,
        db_path: str = ":memory:",
    ) -> "ConsensusResult":
        """Dispatch QA task to multiple agents, then resolve consensus.

        Uses ConsensusValidator to resolve disagreements between agents.
        Agents are run sequentially (simulating parallel for now) and
        results are submitted to the validator.
        """
        from qa_framework.consensus_validator import (
            ConsensusValidator,
            QAOutcome,
            QAResult,
        )

        validator = ConsensusValidator(db_path=db_path)

        for agent_id in agent_ids:
            # Create a sub-task per agent
            sub_task = self.create_task(
                f"[Agent: {agent_id}] {task.history[0].parts[0].get('text', '')}"
                if task.history
                else "QA check",
                context_id=task.id,
            )

            # Run the opencode agent
            try:
                self.dispatch_to_opencode(sub_task.id)
                result_task = self.get_task(sub_task.id)
                assert result_task is not None, f"Task vanished: {sub_task.id}"

                # Determine outcome from task status
                outcome = QAOutcome.INCONCLUSIVE
                if result_task.status == A2ATaskStatus.COMPLETED:
                    outcome = QAOutcome.PASS
                elif result_task.status == A2ATaskStatus.FAILED:
                    outcome = QAOutcome.FAIL

                # Extract evidence from artifacts
                evidence = ""
                if result_task.artifacts:
                    evidence = "\n".join(a.content[:200] for a in result_task.artifacts)

                result = QAResult(
                    agent_id=agent_id,
                    task_id=task.id,
                    outcome=outcome,
                    confidence=0.8 if outcome != QAOutcome.INCONCLUSIVE else 0.5,
                    evidence=evidence,
                )
                validator.submit_result(agent_id, task.id, result)

            except Exception as e:
                # Agent failed to produce result
                result = QAResult(
                    agent_id=agent_id,
                    task_id=task.id,
                    outcome=QAOutcome.INCONCLUSIVE,
                    confidence=0.0,
                    evidence=f"Error: {e}",
                )
                validator.submit_result(agent_id, task.id, result)

        # Resolve consensus
        consensus = validator.resolve(task.id, min_confidence=min_confidence)

        # Update reputations based on outcome
        validator.finalize_task(task.id, consensus)

        return consensus

    def get_agent_health(self, agent_id: str) -> dict[str, object]:
        """Return health status for an agent (circuit breaker + reliability + lock status)."""
        return {
            "agent_id": agent_id,
            "circuit_breaker": self._circuit.get_status(agent_id),
            "reliability": self._reliability.get_metrics(agent_id).__dict__,
        }

    def get_reliability(self, agent_id: str) -> dict[str, object]:
        """Return reliability metrics for an agent."""
        return self._reliability.get_metrics(agent_id).__dict__

    def sanitize_tool_output(self, text: str) -> str:
        """Sanitize tool output text (control chars, length bound)."""
        return self._result_validator.sanitize_text(text)

    def add_session_memory(self, session_id: str, content: str, tier: int = 0) -> int:
        """Add a memory entry for a session."""
        from qa_framework.memory_compactor import MemoryTier
        return self._memory.add_memory(session_id, content, tier=MemoryTier(tier))

    def validate_vision(self, frame: bytes) -> dict[str, object]:
        """Validate a vision frame using AdversarialVisionGuard."""
        import numpy as np
        arr = np.frombuffer(frame, dtype=np.uint8)
        result = self._vision_guard.validate(arr)
        return {
            "score": result.score,
            "warnings": result.warnings,
            "histogram_spread": result.histogram_spread,
            "frame_variance": result.frame_variance,
        }

    def acquire_workspace_lock(self, agent_id: str, file_path: str) -> bool:
        """Acquire a workspace file lock for an agent."""
        return self._locker.acquire_lock(agent_id, file_path)

    def release_workspace_lock(self, agent_id: str, file_path: str) -> None:
        """Release a workspace file lock."""
        self._locker.release_lock(agent_id, file_path)
