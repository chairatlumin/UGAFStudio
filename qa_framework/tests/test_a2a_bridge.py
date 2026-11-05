"""Tests for A2AProtocolBridge."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from qa_framework.a2a_bridge import (
    A2AProtocolBridge,
    A2ATaskStatus,
)


class TestA2AProtocolBridge:
    def _bridge(self):
        return A2AProtocolBridge(url="http://localhost:4096")

    def test_agent_card(self):
        bridge = self._bridge()
        card = bridge.agent_card()
        assert "UGAFStudio" in card["name"]
        assert "capabilities" in card
        assert "skills" in card
        assert card["version"] == "1.0.0"

    def test_create_task(self):
        bridge = self._bridge()
        task = bridge.create_task("test input", context_id="ctx-1")
        assert task.status == A2ATaskStatus.SUBMITTED
        assert task.context_id == "ctx-1"
        assert len(task.history) == 1
        assert task.history[0].role == "user"
        assert task.id is not None

    def test_get_task(self):
        bridge = self._bridge()
        task = bridge.create_task("test")
        fetched = bridge.get_task(task.id)
        assert fetched is not None
        assert fetched.id == task.id

    def test_get_nonexistent_task(self):
        bridge = self._bridge()
        assert bridge.get_task("nonexistent") is None

    def test_update_task_status(self):
        bridge = self._bridge()
        task = bridge.create_task("test")
        updated = bridge.update_task_status(task.id, A2ATaskStatus.WORKING)
        assert updated.status == A2ATaskStatus.WORKING

    def test_update_with_error(self):
        bridge = self._bridge()
        task = bridge.create_task("test")
        updated = bridge.update_task_status(task.id, A2ATaskStatus.FAILED, error="something broke")
        assert updated.status == A2ATaskStatus.FAILED
        assert updated.error == "something broke"

    def test_add_message(self):
        bridge = self._bridge()
        task = bridge.create_task("test")
        updated = bridge.add_message(task.id, "agent", "response text")
        assert len(updated.history) == 2
        assert updated.history[1].role == "agent"
        assert updated.history[1].parts[0]["text"] == "response text"

    def test_add_artifact(self):
        bridge = self._bridge()
        task = bridge.create_task("test")
        updated = bridge.add_artifact(task.id, "code", "print('hello')", metadata={"lang": "python"})
        assert len(updated.artifacts) == 1
        assert updated.artifacts[0].artifact_type == "code"
        assert updated.artifacts[0].metadata["lang"] == "python"

    def test_stream_task(self):
        bridge = self._bridge()
        task = bridge.create_task("test")
        events = list(bridge.stream_task(task.id))
        assert len(events) >= 1
        assert events[0].event == "status"
        assert events[0].task_id == task.id

    def test_stream_with_artifacts(self):
        bridge = self._bridge()
        task = bridge.create_task("test")
        bridge.add_artifact(task.id, "log", "output here")
        events = list(bridge.stream_task(task.id))
        artifact_events = [e for e in events if e.event == "artifact"]
        assert len(artifact_events) == 1
        assert artifact_events[0].data["type"] == "log"

    def test_full_lifecycle(self):
        """Task goes from submitted -> working -> completed."""
        bridge = self._bridge()
        task = bridge.create_task("implement feature X")
        assert task.status == A2ATaskStatus.SUBMITTED

        bridge.update_task_status(task.id, A2ATaskStatus.WORKING)
        task = bridge.get_task(task.id)
        assert task.status == A2ATaskStatus.WORKING

        bridge.add_artifact(task.id, "code", "def foo(): pass")
        bridge.add_message(task.id, "agent", "Task completed successfully")
        bridge.update_task_status(task.id, A2ATaskStatus.COMPLETED)
        task = bridge.get_task(task.id)
        assert task.status == A2ATaskStatus.COMPLETED
        assert len(task.artifacts) == 1
        assert len(task.history) == 2

    def test_dispatch_nonexistent_task(self):
        bridge = self._bridge()
        with pytest.raises(KeyError):
            bridge.dispatch_to_opencode("nonexistent-id")
