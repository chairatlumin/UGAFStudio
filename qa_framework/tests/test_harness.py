"""Tests for the A2A harness layer."""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from qa_framework.harness import (
    AgentConfig,
    DispatchResult,
    DispatchStatus,
    DispatchWrapper,
    PermissionChecker,
    Router,
    TraceLogger,
)

# ─── Router Tests ────────────────────────────────────────────────────────────

def test_router_known_route():
    """Router returns config for known (game_id, task_type)."""
    router = Router()
    config = router.route("4077460", "smoke")
    assert config is not None
    assert config.agent_id == "shinebringer-qa"
    assert config.model == "opencode/nemotron-3.5-lightning-free"


def test_router_unknown_route():
    """Router returns None for unknown (game_id, task_type)."""
    router = Router()
    config = router.route("9999999", "unknown")
    assert config is None


def test_router_gameplay_route():
    """Gameplay route has extended tool set."""
    router = Router()
    config = router.route("4077460", "gameplay")
    assert config is not None
    assert "opencv" in config.tools
    assert "mss" in config.tools


def test_agent_config_immutable():
    """AgentConfig is frozen (immutable)."""
    config = AgentConfig(
        agent_id="test",
        model="test-model",
        working_dir="/tmp",
        tools=frozenset({"pytest"}),
        max_runtime=60,
    )
    with pytest.raises(AttributeError):
        config.agent_id = "modified"  # type: ignore[misc]


# ─── PermissionChecker Tests ─────────────────────────────────────────────────

def test_allowed_command():
    """Allowed tool passes permission check."""
    config = AgentConfig(
        agent_id="test",
        model="test-model",
        working_dir="/tmp",
        tools=frozenset({"pytest", "python", "git"}),
        max_runtime=60,
    )
    checker = PermissionChecker(config)
    allowed, reason = checker.is_allowed("pytest qa_framework/tests/")
    assert allowed is True
    assert reason == "OK"


def test_blocked_tool_not_in_whitelist():
    """Tool not in whitelist is blocked."""
    config = AgentConfig(
        agent_id="test",
        model="test-model",
        working_dir="/tmp",
        tools=frozenset({"pytest"}),
        max_runtime=60,
    )
    checker = PermissionChecker(config)
    allowed, reason = checker.is_allowed("git status")
    assert allowed is False
    assert "not in whitelist" in reason


def test_blocked_deny_pattern():
    """Deny patterns block dangerous commands."""
    config = AgentConfig(
        agent_id="test",
        model="test-model",
        working_dir="/tmp",
        tools=frozenset({"pytest", "git", "rm", "python", "shutdown"}),
        max_runtime=60,
    )
    checker = PermissionChecker(config)
    allowed, reason = checker.is_allowed("rm -rf /tmp/something")
    assert allowed is False
    assert "deny pattern" in reason


def test_blocked_case_insensitive():
    """Permission check is case-insensitive."""
    config = AgentConfig(
        agent_id="test",
        model="test-model",
        working_dir="/tmp",
        tools=frozenset({"pytest"}),
        max_runtime=60,
    )
    checker = PermissionChecker(config)
    allowed, reason = checker.is_allowed("GIT STATUS")
    assert allowed is False


# ─── DispatchWrapper Tests ───────────────────────────────────────────────────

def test_dispatch_unknown_route_escalates():
    """Unknown route returns ESCALATE immediately."""
    wrapper = DispatchWrapper()
    result = wrapper.dispatch("9999999", "unknown", "echo test")
    assert result.status == DispatchStatus.ESCALATE
    assert "No route" in result.reason


def test_dispatch_blocked_command():
    """Blocked command returns BLOCKED immediately."""
    wrapper = DispatchWrapper()
    result = wrapper.dispatch("4077460", "smoke", "rm -rf /tmp/test")
    assert result.status == DispatchStatus.BLOCKED


def test_dispatch_successful_command():
    """Successful command returns SUCCESS."""
    wrapper = DispatchWrapper()
    result = wrapper.dispatch("4077460", "smoke", "python -c \"print('hello')\"")
    assert result.status == DispatchStatus.SUCCESS
    assert result.exit_code == 0
    assert "hello" in result.stdout


def test_dispatch_nonzero_exit_retries():
    """Non-zero exit code triggers retry."""
    wrapper = DispatchWrapper(max_retries=2, base_delay=0.1)
    result = wrapper.dispatch("4077460", "smoke", "python -c \"exit(1)\"")
    assert result.status == DispatchStatus.ESCALATE
    assert result.attempts == 2


def test_dispatch_timeout():
    """Command timeout triggers retry then escalate."""
    wrapper = DispatchWrapper(max_retries=1, base_delay=0.1)
    result = wrapper.dispatch("4077460", "smoke", "python -c \"import time; time.sleep(5)\"", timeout=1)
    assert result.status in (DispatchStatus.TIMEOUT, DispatchStatus.ESCALATE)


# ─── DispatchResult Tests ────────────────────────────────────────────────────

def test_dispatch_result_to_dict():
    """DispatchResult.to_dict() returns expected structure."""
    result = DispatchResult(
        status=DispatchStatus.SUCCESS,
        agent_id="test-agent",
        game_id="4077460",
        task_type="smoke",
        elapsed=1.5,
        attempts=1,
        exit_code=0,
    )
    d = result.to_dict()
    assert d["status"] == "success"
    assert d["agent_id"] == "test-agent"
    assert d["elapsed"] == 1.5


def test_dispatch_result_success_property():
    """success property reflects SUCCESS status."""
    ok = DispatchResult(
        status=DispatchStatus.SUCCESS,
        agent_id="a", game_id="1", task_type="t",
        elapsed=0, attempts=1,
    )
    assert ok.success is True

    fail = DispatchResult(
        status=DispatchStatus.ESCALATE,
        agent_id="a", game_id="1", task_type="t",
        elapsed=0, attempts=1,
    )
    assert fail.success is False


# ─── TraceLogger Tests ───────────────────────────────────────────────────────

def test_trace_logger_writes_file(tmp_path):
    """TraceLogger writes JSON to disk."""
    import json
    logger = TraceLogger(log_dir=str(tmp_path))
    result = DispatchResult(
        status=DispatchStatus.SUCCESS,
        agent_id="test-agent",
        game_id="4077460",
        task_type="smoke",
        elapsed=0.5,
        attempts=1,
        exit_code=0,
    )
    path = logger.log(result)
    assert os.path.exists(path)
    with open(path, "r", encoding="utf-8") as f:
        entry = json.load(f)
    assert entry["status"] == "success"
    assert entry["agent_id"] == "test-agent"
