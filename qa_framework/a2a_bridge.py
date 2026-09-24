"""A2A Protocol Bridge for UGAFStudio — standard Agent2Agent protocol support."""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from enum import Enum
from typing import Generator, NamedTuple, Optional


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


class A2AProtocolBridge:
    """Bridge between UGAFStudio and A2A protocol v1.0."""

    def __init__(
        self,
        agent_name: str = "ugafstudio-agent",
        version: str = "1.0.0",
        url: str = "http://localhost:4096",
    ) -> None:
        self.agent_name = agent_name
        self.version = version
        self.url = url
        self._tasks: dict[str, A2ATask] = {}

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
        self, task_id: str, model: str = "opencode/nemotron-3.5-lightning-free"
    ) -> A2ATask:
        task = self._tasks.get(task_id)
        if task is None:
            raise KeyError(f"Task {task_id} not found")

        self.update_task_status(task_id, A2ATaskStatus.WORKING)

        try:
            user_input = task.history[0].parts[0].get("text", "") if task.history else ""
            cmd = ["opencode", "run", "--model", model, user_input]
            import subprocess

            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=600
            )
            if result.returncode == 0:
                self.add_artifact(task_id, "log", result.stdout)
                self.add_message(task_id, "agent", f"Completed with exit code 0")
                return self.update_task_status(task_id, A2ATaskStatus.COMPLETED)
            else:
                self.add_message(task_id, "agent", f"Failed: {result.stderr[:500]}")
                return self.update_task_status(
                    task_id, A2ATaskStatus.FAILED, error=result.stderr[:500]
                )
        except Exception as e:
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
            QAResult,
            QAOutcome,
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
                sub_task = self.get_task(sub_task.id)

                # Determine outcome from task status
                outcome = QAOutcome.INCONCLUSIVE
                if sub_task and sub_task.status == A2ATaskStatus.COMPLETED:
                    outcome = QAOutcome.PASS
                elif sub_task and sub_task.status == A2ATaskStatus.FAILED:
                    outcome = QAOutcome.FAIL

                # Extract evidence from artifacts
                evidence = ""
                if sub_task and sub_task.artifacts:
                    evidence = "\n".join(a.content[:200] for a in sub_task.artifacts)

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
