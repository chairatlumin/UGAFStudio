from qa_framework.topology.auto_pruner import AutoPruner
from qa_framework.topology.cost_tracker import CoordinationCostTracker
from qa_framework.topology.models import Agent


def test_prunes_high_cost_agents() -> None:
    tracker = CoordinationCostTracker()
    tracker.record_dispatch("expensive-agent", comm_tokens=800, comp_tokens=200)
    agents = [
        Agent(id="expensive-agent", capabilities=["qa"]),
        Agent(id="efficient-agent", capabilities=["qa"]),
    ]
    pruner = AutoPruner(tracker, threshold=0.3)
    active = pruner.get_active_agents(agents)
    assert len(active) == 1
    assert active[0].id == "efficient-agent"


def test_keeps_all_when_under_threshold() -> None:
    tracker = CoordinationCostTracker()
    tracker.record_dispatch("a", comm_tokens=50, comp_tokens=500)
    agents = [Agent(id="a", capabilities=["qa"])]
    pruner = AutoPruner(tracker, threshold=0.3)
    active = pruner.get_active_agents(agents)
    assert len(active) == 1
