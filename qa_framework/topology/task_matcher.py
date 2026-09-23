from __future__ import annotations

from qa_framework.topology.models import Agent, Task


def jaccard_similarity(set_a: set[str], set_b: set[str]) -> float:
    if not set_a or not set_b:
        return 0.0
    intersection = set_a & set_b
    union = set_a | set_b
    return len(intersection) / len(union)


def rank_agents_for_task(task: Task, agents: list[Agent]) -> list[Agent]:
    """Return agents ranked by capability match to task requirements."""
    task_caps = set(task.required_capabilities)
    scored = []
    for agent in agents:
        score = jaccard_similarity(task_caps, set(agent.capabilities))
        if score > 0:
            scored.append((score, agent))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [agent for _, agent in scored]


class TaskMatcher:
    def __init__(self, agents: list[Agent]) -> None:
        self.agents = agents

    def match(self, task: Task, top_k: int = 3) -> list[Agent]:
        ranked = rank_agents_for_task(task, self.agents)
        return ranked[:top_k]
