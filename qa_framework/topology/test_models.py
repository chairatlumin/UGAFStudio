from qa_framework.topology.models import Agent, RouteDecision, TopologyEdge


def test_agent_creation():
    a = Agent(id="unreal-specialist", capabilities=["unreal", "qa"])
    assert a.id == "unreal-specialist"
    assert "unreal" in a.capabilities


def test_topology_edge():
    e = TopologyEdge(source="hermes", target="unreal-specialist", weight=0.95)
    assert e.weight > 0


def test_route_decision():
    d = RouteDecision(
        task_id="test-task",
        selected_agent="unreal-specialist",
        route="direct",
        coordination_cost=0.05,
        confidence=0.92,
    )
    assert d.route == "direct"
