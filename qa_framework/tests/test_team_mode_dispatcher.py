"""Tests for TeamModeDispatcher."""

from __future__ import annotations

import subprocess
import time
from unittest.mock import MagicMock, patch

import pytest

from qa_framework.team_mode_dispatcher import (
    StageResult,
    TeamModeDispatcher,
    TeamResult,
    TeamTask,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_bridge():
    return MagicMock()


@pytest.fixture
def mock_scanner():
    scanner = MagicMock()
    scanner.scan.return_value = MagicMock(
        is_safe=True, findings=[], risk_score=0.0, action="allow"
    )
    return scanner


@pytest.fixture
def dispatcher(mock_bridge, mock_scanner):
    return TeamModeDispatcher(
        bridge=mock_bridge,
        scanner=mock_scanner,
        workdir="C:/Users/Admin/UGAFStudio",
        timeout=30,
    )


@pytest.fixture
def sample_task() -> TeamTask:
    return TeamTask(
        task_id="test-001",
        goal="Add a new feature to the game",
        context={"files": ["game.py", "config.yaml"]},
        plan_agent="opencode/architect",
        exec_agent="opencode/engineer",
        verify_agent="opencode/qa",
        fix_agent="opencode/debug",
    )


def _make_proc(stdout: str, returncode: int = 0):
    proc = MagicMock()
    proc.communicate.return_value = (stdout, "")
    proc.returncode = returncode
    proc.kill = MagicMock()
    return proc


# ---------------------------------------------------------------------------
# Data model construction
# ---------------------------------------------------------------------------

def test_stage_result_namedtuple():
    sr = StageResult(stage="plan", agent_id="agent-1", output="plan text",
                     exit_code=0, duration_s=1.23)
    assert sr.stage == "plan"
    assert sr.exit_code == 0


def test_team_task_namedtuple():
    task = TeamTask(task_id="t1", goal="goal", context={},
                    plan_agent="p", exec_agent="e", verify_agent="v", fix_agent="f")
    assert task.task_id == "t1"
    assert task.plan_agent == "p"


def test_team_result_namedtuple():
    tr = TeamResult(task_id="t1", status="success", stages=[],
                    final_output="done", total_time_s=5.0)
    assert tr.status == "success"
    assert tr.final_output == "done"


# ---------------------------------------------------------------------------
# _run_stage
# ---------------------------------------------------------------------------

def test_run_stage_success(dispatcher: TeamModeDispatcher):
    proc = _make_proc("Plan complete\nEXIT=0")
    with patch("subprocess.Popen", return_value=proc) as mock_popen:
        result = dispatcher._run_stage("plan", "opencode/architect", "Brief text")

    assert result.stage == "plan"
    assert result.agent_id == "opencode/architect"
    assert result.exit_code == 0
    assert "Plan complete" in result.output
    assert result.duration_s >= 0.0
    mock_popen.assert_called_once()


def test_run_stage_timeout(dispatcher: TeamModeDispatcher):
    proc = MagicMock()
    proc.communicate.side_effect = [
        subprocess.TimeoutExpired(cmd="opencode", timeout=30),
        ("", ""),  # After kill
    ]
    proc.kill = MagicMock()
    proc.returncode = -9

    with patch("subprocess.Popen", return_value=proc):
        result = dispatcher._run_stage("exec", "opencode/engineer", "Brief")

    proc.kill.assert_called_once()
    assert result.exit_code == -9


# ---------------------------------------------------------------------------
# Brief generators
# ---------------------------------------------------------------------------

def test_brief_plan(sample_task: TeamTask):
    brief = TeamModeDispatcher._brief_plan(sample_task)
    assert "Add a new feature" in brief
    assert "game.py" in brief
    assert "software architect" in brief


def test_brief_exec(sample_task: TeamTask):
    brief = TeamModeDispatcher._brief_exec(sample_task, "Step 1: do X")
    assert "Step 1: do X" in brief
    assert "engineer" in brief


def test_brief_verify(sample_task: TeamTask):
    brief = TeamModeDispatcher._brief_verify(sample_task, "Implemented feature")
    assert "Add a new feature" in brief
    assert "Implemented feature" in brief
    assert "QA verifier" in brief


def test_brief_fix(sample_task: TeamTask):
    brief = TeamModeDispatcher._brief_fix(sample_task, "impl", "FAIL: test X")
    assert "FAIL: test X" in brief
    assert "debug" in brief


# ---------------------------------------------------------------------------
# Full pipeline
# ---------------------------------------------------------------------------

def test_dispatch_team_success(dispatcher: TeamModeDispatcher, sample_task: TeamTask):
    """Plan → Exec → Verify (pass) → SUCCESS"""
    plan_proc = _make_proc("Step 1: design X\nEXIT=0", 0)
    exec_proc = _make_proc("Implemented X\nEXIT=0", 0)
    verify_proc = _make_proc("All tests pass\nEXIT=0", 0)

    with patch("subprocess.Popen", side_effect=[plan_proc, exec_proc, verify_proc]):
        result = dispatcher.dispatch_team(sample_task)

    assert result.task_id == "test-001"
    assert result.status == "success"
    assert len(result.stages) == 3
    assert result.final_output is not None
    assert "Implemented X" in result.final_output
    assert result.total_time_s >= 0.0


def test_dispatch_team_plan_fails(dispatcher: TeamModeDispatcher, sample_task: TeamTask):
    """Plan fails → FAILED, no exec/verify"""
    plan_proc = _make_proc("Error: cannot proceed", 1)

    with patch("subprocess.Popen", return_value=plan_proc):
        result = dispatcher.dispatch_team(sample_task)

    assert result.status == "failed"
    assert len(result.stages) == 1
    assert result.final_output is None


def test_dispatch_team_verify_fails_then_fix(dispatcher: TeamModeDispatcher, sample_task: TeamTask):
    """Plan → Exec → Verify (fail) → Fix → Verify (pass) → SUCCESS"""
    plan_proc = _make_proc("Plan done", 0)
    exec_proc = _make_proc("Code done", 0)
    verify_fail = _make_proc("FAIL: test X", 1)
    fix_proc = _make_proc("Fixed", 0)
    verify_pass = _make_proc("PASS", 0)

    with patch("subprocess.Popen", side_effect=[plan_proc, exec_proc, verify_fail, fix_proc, verify_pass]):
        result = dispatcher.dispatch_team(sample_task)

    assert result.status == "success"
    assert len(result.stages) == 5
    stages = [s.stage for s in result.stages]
    assert stages == ["plan", "exec", "verify", "fix", "verify"]


def test_dispatch_team_verify_fails_max_iterations(dispatcher: TeamModeDispatcher, sample_task: TeamTask):
    """Verify fails 2 times → PARTIAL"""
    plan_proc = _make_proc("Plan done", 0)
    exec_proc = _make_proc("Code done", 0)
    verify_fail = _make_proc("FAIL", 1)
    fix_proc = _make_proc("Fixed attempt", 0)
    # Both fix iterations also fail verification
    verify_fail_2 = _make_proc("STILL FAIL", 1)

    with patch("subprocess.Popen", side_effect=[
        plan_proc, exec_proc, verify_fail, fix_proc, verify_fail_2, fix_proc, verify_fail_2
    ]):
        result = dispatcher.dispatch_team(sample_task)

    assert result.status == "partial"
    # plan, exec, verify, fix, verify, fix, verify = 7 stages
    assert len(result.stages) == 7


# ---------------------------------------------------------------------------
# _result helper
# ---------------------------------------------------------------------------

def test_result_helper(dispatcher: TeamModeDispatcher, sample_task: TeamTask):
    stage = StageResult(stage="plan", agent_id="a", output="o", exit_code=0, duration_s=1.0)
    result = dispatcher._result(sample_task, "success", [stage], "final", time.time())

    assert isinstance(result, TeamResult)
    assert result.task_id == "test-001"
    assert result.status == "success"
    assert result.final_output == "final"
