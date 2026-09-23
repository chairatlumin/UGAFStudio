from __future__ import annotations

from qa_framework.topology.cost_tracker import CoordinationCostTracker
from qa_framework.topology.models import Agent


class AutoPruner:
    def __init__(self, cost_tracker: CoordinationCostTracker, threshold: float = 0.3):
        self.tracker = cost_tracker
        self.threshold = threshold

    def get_active_agents(self, all_agents: list[Agent]) -> list[Agent]:
        """Return agents under coordination cost threshold."""
        flagged = set(self.tracker.get_flagged_agents(self.threshold))
        return [a for a in all_agents if a.id not in flagged]

    def get_pruned_agents(self, all_agents: list[Agent]) -> list[Agent]:
        """Return agents over coordination cost threshold (deprioritized)."""
        flagged = set(self.tracker.get_flagged_agents(self.threshold))
        return [a for a in all_agents if a.id in flagged]
