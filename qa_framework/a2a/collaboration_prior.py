"""Collaboration prior data models for A2A orchestration."""
from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional


class CollaborationPrior(BaseModel):
    task_type: str
    source_agent: str
    target_agent: str
    success_count: int = 0
    failure_count: int = 0
    avg_execution_time: float = 0.0
    last_used: Optional[datetime] = None

    @property
    def success_rate(self) -> float:
        total = self.success_count + self.failure_count
        return self.success_count / total if total > 0 else 0.0


class CollaborationResult(BaseModel):
    task_id: str
    source_agent: str
    target_agent: str
    success: bool
    execution_time: float
    timestamp: datetime = Field(default_factory=datetime.now)
    error_message: Optional[str] = None
