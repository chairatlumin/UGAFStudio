from __future__ import annotations

from pydantic import BaseModel


class AgentCostStats(BaseModel):
    agent_id: str
    total_comm_tokens: int = 0
    total_comp_tokens: int = 0
    dispatch_count: int = 0

    @property
    def comm_ratio(self) -> float:
        total = self.total_comm_tokens + self.total_comp_tokens
        if total == 0:
            return 0.0
        return self.total_comm_tokens / total


class CoordinationCostTracker:
    def __init__(self) -> None:
        self._stats: dict[str, AgentCostStats] = {}

    def record_dispatch(self, agent_id: str, comm_tokens: int, comp_tokens: int) -> None:
        if agent_id not in self._stats:
            self._stats[agent_id] = AgentCostStats(agent_id=agent_id)
        s = self._stats[agent_id]
        s.total_comm_tokens += comm_tokens
        s.total_comp_tokens += comp_tokens
        s.dispatch_count += 1

    def get_agent_stats(self, agent_id: str) -> AgentCostStats:
        if agent_id not in self._stats:
            self._stats[agent_id] = AgentCostStats(agent_id=agent_id)
        return self._stats[agent_id]

    def get_flagged_agents(self, threshold: float = 0.3) -> list[str]:
        return [s.agent_id for s in self._stats.values() if s.comm_ratio > threshold]

    def get_all_stats(self) -> dict[str, AgentCostStats]:
        return dict(self._stats)
