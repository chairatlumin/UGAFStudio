from qa_framework.mcp_adapter import MCPResourceAdapter


def test_tool_listing():
    adapter = MCPResourceAdapter()
    tools = adapter.list_tools()
    assert len(tools) >= 4
    names = [t["name"] for t in tools]
    assert "list_game_tests" in names


def test_run_game_test_returns_result():
    adapter = MCPResourceAdapter()
    result = adapter.call_tool("run_game_test", {"scenario": "test_combat"})
    assert "scenario" in result
    assert "success" in result


def test_unknown_tool_returns_error():
    adapter = MCPResourceAdapter()
    result = adapter.call_tool("nonexistent_tool", {})
    assert "error" in result
