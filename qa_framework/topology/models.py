from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class Agent(BaseModel):
    id: str
    capabilities: list[str]
    cost_per_token: float = 0.0
    avg_latency_ms: float = 0.0
    success_rate: float = 1.0
    coordination_cost: float = 0.0


class Task(BaseModel):
    id: str
    goal: str
    required_capabilities: list[str]
    context: dict = Field(default_factory=dict)
    priority: int = 5  # 1-10


class TopologyEdge(BaseModel):
    source: str
    target: str
    weight: float  # 0-1, higher = better match
    latency_ms: float = 0.0
    last_used: float = 0.0  # timestamp


class RouteDecision(BaseModel):
    task_id: str
    selected_agent: str
    route: Literal["direct", "a2a-mediated", "compound"]
    coordination_cost: float
    confidence: float
