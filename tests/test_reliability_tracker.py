"""Tests for ReliabilityTracker."""
from __future__ import annotations

from qa_framework.reliability_tracker import DispatchOutcome, ReliabilityTracker


class TestReliabilityTracker:
    def test_record_dispatch_outcome(self) -> None:
        tracker = ReliabilityTracker(db_path=":memory:")
        tracker.record_dispatch(
            agent_id="opencode",
            task_type="code_gen",
            model="opencode/nemotron-3.5-lightning-free",
            outcome=DispatchOutcome.SUCCESS,
            duration_ms=2500,
            confidence=0.85,
        )
        score = tracker.get_reliability_score("opencode")
        assert 0.0 <= score <= 1.0

    def test_repeatability_computation(self) -> None:
        tracker = ReliabilityTracker(db_path=":memory:")
        # 3 successes out of 4 dispatches → repeatability = 0.75
        for _ in range(3):
            tracker.record_dispatch("agent_a", "test", "m", DispatchOutcome.SUCCESS, 100, 0.9)
        tracker.record_dispatch("agent_a", "test", "m", DispatchOutcome.FAILURE, 100, 0.3)
        metrics = tracker.get_metrics("agent_a")
        assert metrics.repeatability == 0.75

    def test_failure_severity_with_mixed_outcomes(self) -> None:
        tracker = ReliabilityTracker(db_path=":memory:")
        tracker.record_dispatch("agent_b", "t", "m", DispatchOutcome.FAILURE, 100, 0.2)
        tracker.record_dispatch("agent_b", "t", "m", DispatchOutcome.SUCCESS, 100, 0.8)
        metrics = tracker.get_metrics("agent_b")
        assert metrics.failure_severity == 0.7  # FAILURE weight

    def test_empty_agent_returns_default_metrics(self) -> None:
        tracker = ReliabilityTracker(db_path=":memory:")
        metrics = tracker.get_metrics("nonexistent")
        assert metrics.total_dispatches == 0
        assert metrics.score == 0.5

    def test_get_agents_returns_all_tracked(self) -> None:
        tracker = ReliabilityTracker(db_path=":memory:")
        tracker.record_dispatch("agent_x", "t", "m", DispatchOutcome.SUCCESS, 100, 0.9)
        tracker.record_dispatch("agent_y", "t", "m", DispatchOutcome.SUCCESS, 100, 0.9)
        agents = tracker.get_agents()
        assert "agent_x" in agents
        assert "agent_y" in agents

    def test_variance_computation(self) -> None:
        tracker = ReliabilityTracker(db_path=":memory:")
        # High variance in confidence
        for i in range(10):
            tracker.record_dispatch(
                "agent_v", "t", "m", DispatchOutcome.SUCCESS, 100, float(i) / 10
            )
        metrics = tracker.get_metrics("agent_v")
        assert metrics.variance > 0.0

    def test_prune_old_records(self) -> None:
        tracker = ReliabilityTracker(db_path=":memory:")
        # Manually insert old record
        tracker.record_dispatch("agent_z", "t", "m", DispatchOutcome.SUCCESS, 100, 0.9)
        # Update timestamp to old
        import time
        old_time = time.time() - (40 * 86400)  # 40 days old
        tracker._conn.execute(
            "UPDATE dispatch_outcomes SET timestamp = ? WHERE agent_id = ?",
            (old_time, "agent_z"),
        )
        tracker._conn.commit()
        pruned = tracker.prune_old_records(max_age_days=30)
        assert pruned == 1

    def test_calibration_requires_min_samples(self) -> None:
        tracker = ReliabilityTracker(db_path=":memory:")
        # Less than 5 samples → calibration is None
        for _ in range(3):
            tracker.record_dispatch("agent_c", "t", "m", DispatchOutcome.SUCCESS, 100, 0.9)
        metrics = tracker.get_metrics("agent_c")
        assert metrics.calibration is None

    def test_dispatch_outcome_enum_values(self) -> None:
        assert DispatchOutcome.SUCCESS.value == "success"
        assert DispatchOutcome.FAILURE.value == "failure"
        assert DispatchOutcome.TIMEOUT.value == "timeout"
        assert DispatchOutcome.BLOCKED.value == "blocked"
