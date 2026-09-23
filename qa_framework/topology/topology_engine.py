from __future__ import annotations

from typing import Literal

from qa_framework.topology.models import Agent, RouteDecision, Task, TopologyEdge
from qa_framework.topology.task_matcher import rank_agents_for_task

CONFIDENCE_THRESHOLD_DIRECT = 0.85
CONFIDENCE_THRESHOLD_COMPOUND = 0.50


class TopologyEngine:
    def __init__(self) -> None:
        self.agents: dict[str, Agent] = {}
        self.edges: list[TopologyEdge] = []
        self.decision_log: list[RouteDecision] = []

    def register_agent(self, agent: Agent) -> None:
        self.agents[agent.id] = agent

    def decide_route(self, task: Task) -> RouteDecision:
        ranked = rank_agents_for_task(task, list(self.agents.values()))

        if not ranked:
            decision = RouteDecision(
                task_id=task.id,
                selected_agent="",
                route="a2a-mediated",
                coordination_cost=1.0,
                confidence=0.0,
            )
            self.decision_log.append(decision)
            return decision

        best = ranked[0]
        task_caps = set(task.required_capabilities)
        best_caps = set(best.capabilities)
        confidence = len(task_caps & best_caps) / len(task_caps) if task_caps else 0.0

        if confidence >= CONFIDENCE_THRESHOLD_DIRECT:
            route: Literal["direct", "a2a-mediated", "compound"] = "direct"
            coord_cost = 0.05
        elif confidence >= CONFIDENCE_THRESHOLD_COMPOUND:
            route = "compound"
            coord_cost = 0.30
        else:
            route = "a2a-mediated"
            coord_cost = 0.60

        decision = RouteDecision(
            task_id=task.id,
            selected_agent=best.id,
            route=route,
            coordination_cost=coord_cost,
            confidence=confidence,
        )
        self.decision_log.append(decision)
        return decision
