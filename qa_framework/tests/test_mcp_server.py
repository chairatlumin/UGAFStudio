"""Tests for MCP server and tools."""

from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_mcp_tools_importable():
    """MCP tools module imports cleanly."""
    from qa_framework.mcp_tools import list_checkpoints_tool, run_qa_tool

    assert callable(run_qa_tool)
    assert callable(list_checkpoints_tool)


def test_mcp_server_importable():
    """MCP server module imports cleanly."""
    from qa_framework.mcp_server import mcp

    assert mcp is not None


def test_mcp_server_has_tools():
    """MCP server has expected tools registered."""
    from qa_framework.mcp_server import mcp

    tools = asyncio.run(mcp.list_tools())
    tool_names = [t.name for t in tools]
    assert "run_qa" in tool_names
    assert "list_checkpoints" in tool_names
    assert "get_cost_summary" in tool_names
    assert "get_recovery_summary" in tool_names
    assert "start_qa_campaign" in tool_names
    assert "list_qa_campaigns" in tool_names
    assert "retry_qa_campaign" in tool_names


def test_list_checkpoints_tool_returns_expected_keys():
    """list_checkpoints_tool returns suite name and checkpoints list."""
    from qa_framework.mcp_tools import list_checkpoints_tool

    suite_data = {
        "name": "test-suite",
        "tests": [
            {
                "name": "tc1",
                "steps": [{"name": "s1", "check": "file_exists", "path": "."}],
            }
        ],
    }
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False
    ) as f:
        json.dump(suite_data, f)
        tmppath = f.name

    try:
        result = list_checkpoints_tool(tmppath)
        assert "suite" in result
        assert "checkpoints" in result
        assert result["suite"] == "test-suite"
        assert len(result["checkpoints"]) >= 1
    finally:
        os.unlink(tmppath)


def test_run_qa_tool_with_verification():
    """run_qa_tool runs suite and returns structured result."""
    from qa_framework.mcp_tools import run_qa_tool

    suite_data = {
        "name": "verify-suite",
        "tests": [
            {
                "name": "exists",
                "steps": [
                    {
                        "name": "dir-check",
                        "check": "directory_exists",
                        "path": ".",
                    }
                ],
            }
        ],
    }
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False
    ) as f:
        json.dump(suite_data, f)
        tmppath = f.name

    try:
        result = run_qa_tool(tmppath, enable_verification=True)
        assert result["tests_total"] == 1
        assert "passed" in result
        assert "failed" in result
        assert "results" in result
    finally:
        os.unlink(tmppath)


def test_get_cost_tracker_tool_returns_summary():
    """get_cost_tracker_tool returns a summary dict."""
    from qa_framework.mcp_tools import get_cost_tracker_tool

    result = get_cost_tracker_tool()
    assert "total_tokens" in result
    assert "total_cost_usd" in result


def test_get_recovery_tracker_tool_returns_summary():
    """get_recovery_tracker_tool returns a summary dict."""
    from qa_framework.mcp_tools import get_recovery_tracker_tool

    result = get_recovery_tracker_tool()
    assert "incidents" in result
    assert "recoveries" in result
    assert "recovery_rate" in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
