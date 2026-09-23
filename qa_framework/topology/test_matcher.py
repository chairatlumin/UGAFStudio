from qa_framework.topology.models import Agent, Task
from qa_framework.topology.task_matcher import TaskMatcher, rank_agents_for_task


def test_exact_match() -> None:
    agents = [Agent(id="qa-lead", capabilities=["qa", "testing"])]
    task = Task(id="t1", goal="test", required_capabilities=["qa"])
    result = rank_agents_for_task(task, agents)
    assert result[0].id == "qa-lead"


def test_partial_match_scoring() -> None:
    agents = [
        Agent(id="a", capabilities=["qa"]),
        Agent(id="b", capabilities=["qa", "testing", "docs"]),
    ]
    task = Task(id="t1", goal="test", required_capabilities=["qa", "testing"])
    result = rank_agents_for_task(task, agents)
    assert result[0].id == "b"


def test_no_match_returns_empty() -> None:
    agents = [Agent(id="a", capabilities=["unreal"])]
    task = Task(id="t1", goal="test", required_capabilities=["qa"])
    result = rank_agents_for_task(task, agents)
    assert len(result) == 0


def test_matcher_top_k() -> None:
    agents = [
        Agent(id="a", capabilities=["qa"]),
        Agent(id="b", capabilities=["qa", "testing"]),
    ]
    task = Task(id="t1", goal="test", required_capabilities=["qa"])
    matcher = TaskMatcher(agents)
    assert len(matcher.match(task, top_k=1)) == 1
