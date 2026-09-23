from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class MCPResourceAdapter:
    """Exposes A2A game QA tools as MCP-compatible JSON-RPC resources."""
    _tools: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        self._tools = {
            "list_game_tests": self._list_game_tests,
            "run_game_test": self._run_game_test,
            "get_test_results": self._get_test_results,
            "get_game_state": self._get_game_state,
        }

    def list_tools(self) -> list[dict]:
        return [
            {"name": "list_game_tests", "description": "List all available game test scenarios",
             "inputSchema": {"type": "object", "properties": {}}},
            {"name": "run_game_test", "description": "Run a specific game test scenario",
             "inputSchema": {"type": "object", "properties": {"scenario": {"type": "string"}},
                           "required": ["scenario"]}},
            {"name": "get_test_results", "description": "Get results from a test run",
             "inputSchema": {"type": "object", "properties": {"run_id": {"type": "string"}}}},
            {"name": "get_game_state", "description": "Get current game state from perception",
             "inputSchema": {"type": "object", "properties": {}}},
        ]

    def call_tool(self, name: str, arguments: dict) -> dict[str, Any]:
        if name not in self._tools:
            return {"error": f"Unknown tool: {name}"}
        try:
            result = self._tools[name](arguments)
            if isinstance(result, dict):
                return result
            return {"error": "Tool returned non-dict"}
        except Exception as e:
            return {"error": str(e)}

    def _list_game_tests(self, arguments: dict) -> dict:
        return {"scenarios": ["test_combat", "test_tutorial", "test_menu_navigation"]}

    def _run_game_test(self, arguments: dict) -> dict:
        scenario = arguments.get("scenario", "default")
        return {"scenario": scenario, "success": True, "steps_taken": 5}

    def _get_test_results(self, arguments: dict) -> dict:
        run_id = arguments.get("run_id", "last")
        return {"run_id": run_id, "results": [{"scenario": "test_combat", "success": True}]}

    def _get_game_state(self, arguments: dict) -> dict:
        return {"scene_classification": "gameplay", "confidence": 0.9}
