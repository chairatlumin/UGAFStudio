"""Tests for collaboration tracker."""
from qa_framework.a2a.collaboration_tracker import CollaborationTracker
from qa_framework.a2a.collaboration_prior import CollaborationResult


def test_tracker_records_success():
    tracker = CollaborationTracker(db_path=":memory:")
    result = CollaborationResult(
        task_id="task-1",
        source_agent="hermes",
        target_agent="opencode",
        success=True,
        execution_time=2.5
    )
    tracker.record(result)
    priors = tracker.get_priors("hermes", "opencode")
    assert len(priors) == 1
    assert priors[0].success_count == 1


def test_tracker_records_failure():
    tracker = CollaborationTracker(db_path=":memory:")
    result = CollaborationResult(
        task_id="task-2",
        source_agent="hermes",
        target_agent="opencode",
        success=False,
        execution_time=1.0,
        error_message="timeout"
    )
    tracker.record(result)
    priors = tracker.get_priors("hermes", "opencode")
    assert len(priors) == 1
    assert priors[0].failure_count == 1


def test_tracker_suggests_best_agent():
    tracker = CollaborationTracker(db_path=":memory:")
    for i in range(5):
        tracker.record(CollaborationResult(
            task_id=f"task-{i}",
            source_agent="hermes",
            target_agent="opencode",
            success=True,
            execution_time=2.0
        ))
    for i in range(3):
        tracker.record(CollaborationResult(
            task_id=f"task-fail-{i}",
            source_agent="hermes",
            target_agent="other_agent",
            success=False,
            execution_time=1.0
        ))
    best = tracker.suggest_best_agent("hermes", ["opencode", "other_agent"])
    assert best == "opencode"
