from qa_framework.topology.models import Agent, Task
from qa_framework.topology.topology_engine import TopologyEngine


def test_direct_route_for_high_confidence() -> None:
    engine = TopologyEngine()
    engine.register_agent(Agent(id="qa-lead", capabilities=["qa", "testing"]))
    task = Task(id="t1", goal="run tests", required_capabilities=["qa"])
    decision = engine.decide_route(task)
    assert decision.route == "direct"
    assert decision.selected_agent == "qa-lead"


def test_a2a_route_for_low_confidence() -> None:
    engine = TopologyEngine()
    engine.register_agent(Agent(id="a", capabilities=["unreal"]))
    task = Task(id="t1", goal="complex task", required_capabilities=["qa", "unreal", "docs"])
    decision = engine.decide_route(task)
    assert decision.route in ("a2a-mediated", "compound")


def test_route_records_decision() -> None:
    engine = TopologyEngine()
    engine.register_agent(Agent(id="qa-lead", capabilities=["qa"]))
    task = Task(id="t1", goal="test", required_capabilities=["qa"])
    engine.decide_route(task)
    assert len(engine.decision_log) == 1
