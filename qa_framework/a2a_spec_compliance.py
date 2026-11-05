from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class AgentCard:
    """A2A Protocol v1.0 Agent Card descriptor."""
    name: str
    description: str
    version: str
    url: str = "http://localhost:4096"
    capabilities: list[str] = field(default_factory=list)
    authentication: dict = field(default_factory=lambda: {"type": "none"})
    provider: Optional[dict] = None
    skills: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        result = {
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "url": self.url,
            "capabilities": self.capabilities,
            "authentication": self.authentication,
        }
        if self.provider:
            result["provider"] = self.provider
        if self.skills:
            result["skills"] = self.skills
        return result

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)

    def validate(self) -> list[str]:
        errors = []
        if not self.name:
            errors.append("name required")
        if not self.version:
            errors.append("version required")
        if not self.capabilities:
            errors.append("at least one capability required")
        auth_type = self.authentication.get("type")
        if auth_type not in ("none", "oauth2", "jwt", "mtls"):
            errors.append(f"unsupported auth type: {auth_type}")
        return errors


@dataclass
class TaskLifecycle:
    """A2A Protocol v1.0 task lifecycle state machine."""
    task_id: str
    state: str = "submitted"
    history: list[dict] = field(default_factory=list)
    artifacts: list[dict] = field(default_factory=list)

    _VALID_TRANSITIONS = {
        "submitted": ["working", "canceled"],
        "working": ["completed", "failed", "input-required", "canceled"],
        "input-required": ["working", "canceled"],
        "completed": [],
        "failed": [],
        "canceled": [],
    }

    def transition(self, new_state: str) -> None:
        allowed = self._VALID_TRANSITIONS.get(self.state, [])
        if new_state not in allowed:
            raise ValueError(f"Invalid transition: {self.state} -> {new_state}")
        self.state = new_state

    def add_message(self, role: str, text: str, metadata: Optional[dict] = None) -> None:
        self.history.append({
            "role": role,
            "parts": [{"type": "text", "text": text}],
            "metadata": metadata or {},
        })

    def add_artifact(self, artifact_type: str, content: str, metadata: Optional[dict] = None) -> None:
        import uuid
        self.artifacts.append({
            "artifact_id": str(uuid.uuid4()),
            "artifact_type": artifact_type,
            "content": content,
            "metadata": metadata or {},
        })

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "state": self.state,
            "history": self.history,
            "artifacts": self.artifacts,
        }
