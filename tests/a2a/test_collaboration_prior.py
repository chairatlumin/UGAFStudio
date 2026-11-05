"""Tests for collaboration prior data models."""
from qa_framework.a2a.collaboration_prior import CollaborationPrior, CollaborationResult


def test_collaboration_prior_creation():
    prior = CollaborationPrior(
        task_type="code_generation",
        source_agent="hermes",
        target_agent="opencode",
        success_count=10,
        failure_count=2,
        avg_execution_time=5.5
    )
    assert prior.task_type == "code_generation"
    assert prior.source_agent == "hermes"
    assert prior.target_agent == "opencode"
    assert prior.success_rate == 10 / 12


def test_collaboration_result_creation():
    result = CollaborationResult(
        task_id="task-123",
        source_agent="hermes",
        target_agent="opencode",
        success=True,
        execution_time=3.2
    )
    assert result.task_id == "task-123"
    assert result.success == True
