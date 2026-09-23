from qa_framework.topology.cost_tracker import CoordinationCostTracker


def test_records_agent_cost() -> None:
    tracker = CoordinationCostTracker()
    tracker.record_dispatch("qa-lead", comm_tokens=50, comp_tokens=500)
    stats = tracker.get_agent_stats("qa-lead")
    assert stats.comm_ratio == 50 / 550


def test_flags_high_coordination() -> None:
    tracker = CoordinationCostTracker()
    tracker.record_dispatch("qa-lead", comm_tokens=500, comp_tokens=500)
    flagged = tracker.get_flagged_agents(threshold=0.3)
    assert "qa-lead" in flagged


def test_no_flag_for_efficient_agent() -> None:
    tracker = CoordinationCostTracker()
    tracker.record_dispatch("qa-lead", comm_tokens=50, comp_tokens=500)
    flagged = tracker.get_flagged_agents(threshold=0.3)
    assert "qa-lead" not in flagged
