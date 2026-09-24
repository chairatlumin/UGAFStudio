"""Integration tests for ReliabilityTracker, ToolResultValidator, MemoryCompactor
in A2AProtocolBridge."""
from __future__ import annotations

from qa_framework.a2a_bridge import A2AProtocolBridge, A2ATaskStatus
from qa_framework.memory_compactor import MemoryCompactor
from qa_framework.reliability_tracker import ReliabilityTracker
from qa_framework.tool_result_validator import ToolResultValidator


class TestBridgeReliabilityIntegration:
    def test_bridge_has_reliability_tracker(self) -> None:
        bridge = A2AProtocolBridge()
        assert hasattr(bridge, '_reliability')
        assert isinstance(bridge._reliability, ReliabilityTracker)

    def test_bridge_has_result_validator(self) -> None:
        bridge = A2AProtocolBridge()
        assert hasattr(bridge, '_result_validator')
        assert isinstance(bridge._result_validator, ToolResultValidator)

    def test_bridge_has_memory_compactor(self) -> None:
        bridge = A2AProtocolBridge()
        assert hasattr(bridge, '_memory')
        assert isinstance(bridge._memory, MemoryCompactor)

    def test_get_reliability_method_exists(self) -> None:
        bridge = A2AProtocolBridge()
        result = bridge.get_reliability("test_agent")
        assert isinstance(result, dict)
        assert "agent_id" in result or "score" in result

    def test_sanitize_tool_output_method(self) -> None:
        bridge = A2AProtocolBridge()
        text = "Hello\x00World\x07Test"
        result = bridge.sanitize_tool_output(text)
        assert "\x00" not in result
        assert "\x07" not in result

    def test_add_session_memory_method(self) -> None:
        bridge = A2AProtocolBridge()
        # Use in-memory DB
        bridge._memory = MemoryCompactor(db_path=":memory:")
        result = bridge.add_session_memory("test_session", "test content", tier=0)
        assert isinstance(result, int)

    def test_health_includes_reliability(self) -> None:
        bridge = A2AProtocolBridge()
        health = bridge.get_agent_health("test_agent")
        assert "reliability" in health
        assert "circuit_breaker" in health


class TestBridgeDispatchReliability:
    def test_dispatch_records_reliability(self, monkeypatch) -> None:
        """Test that dispatch records reliability outcome."""
        bridge = A2AProtocolBridge()
        task = bridge.create_task("test prompt")

        # Mock subprocess.run to avoid actually running opencode
        class MockResult:
            returncode = 0
            stdout = '{"status": "ok"}'
            stderr = ""

        import subprocess
        monkeypatch.setattr(subprocess, "run", lambda *a, **kw: MockResult())

        result = bridge.dispatch_to_opencode(task.id)
        assert result.status == A2ATaskStatus.COMPLETED

        # Check reliability was recorded
        metrics = bridge.get_reliability("opencode")
        assert metrics["total_dispatches"] >= 1

    def test_dispatch_failure_records_reliability(self, monkeypatch) -> None:
        """Test that failed dispatch records failure outcome."""
        bridge = A2AProtocolBridge()
        task = bridge.create_task("test prompt")

        class MockResult:
            returncode = 1
            stdout = ""
            stderr = "error occurred"

        import subprocess
        monkeypatch.setattr(subprocess, "run", lambda *a, **kw: MockResult())

        result = bridge.dispatch_to_opencode(task.id)
        assert result.status == A2ATaskStatus.FAILED

        metrics = bridge.get_reliability("opencode")
        assert metrics["total_dispatches"] >= 1


class TestEndToEndValidation:
    def test_json_output_validation_in_dispatch(self, monkeypatch) -> None:
        """Test that JSON output from dispatch is validated."""
        bridge = A2AProtocolBridge()
        task = bridge.create_task("generate json")

        class MockResult:
            returncode = 0
            stdout = '{"valid": "json"}'
            stderr = ""

        import subprocess
        monkeypatch.setattr(subprocess, "run", lambda *a, **kw: MockResult())

        result = bridge.dispatch_to_opencode(task.id)
        # Should complete successfully
        assert result.status == A2ATaskStatus.COMPLETED

    def test_invalid_json_output_gets_warning(self, monkeypatch) -> None:
        """Test that invalid JSON output generates a warning message."""
        bridge = A2AProtocolBridge()
        task = bridge.create_task("generate bad json")

        class MockResult:
            returncode = 0
            stdout = '{invalid json: missing quotes}'
            stderr = ""

        import subprocess
        monkeypatch.setattr(subprocess, "run", lambda *a, **kw: MockResult())

        result = bridge.dispatch_to_opencode(task.id)
        # Check if warning message was added
        has_warning = any(
            "JSON parse warning" in msg.parts[0].get("text", "")
            for msg in result.history
        )
        assert has_warning
