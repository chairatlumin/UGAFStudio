"""Tests for A2AProtocolBridge lesson integration."""

from __future__ import annotations

from qa_framework.a2a_bridge import A2AProtocolBridge


def test_bridge_quessons_before_dispatch() -> None:
    from qa_framework.a2a_bridge import A2AProtocolBridge

    bridge = A2AProtocolBridge()
    bridge.lesson_bus.publish("agent-1", "pattern-x", "solution-y", ["tag1"], 0.9)
    lessons = bridge.get_relevant_lessons("task with pattern-x", ["tag1"])
    assert len(lessons) == 1
    assert lessons[0]["solution"] == "solution-y"


def test_bridge_publish_lesson_roundtrip() -> None:
    bridge = A2AProtocolBridge()
    lesson_id = bridge.publish_lesson(
        agent_id="agent-1",
        pattern="D3D12 fence wait timeout",
        solution="flush command queue before wait",
        tags=["d3d12", "gpu"],
        confidence=0.9,
    )
    assert lesson_id > 0
    lessons = bridge.get_relevant_lessons("D3D12 fence wait", ["gpu"])
    assert len(lessons) == 1
    assert lessons[0]["solution"] == "flush command queue before wait"


def test_bridge_lessons_respect_tag_filter() -> None:
    bridge = A2AProtocolBridge()
    bridge.publish_lesson("a1", "shared widget crash", "fix widget", ["ui"], 0.8)
    bridge.publish_lesson("a2", "shared socket crash", "fix socket", ["net"], 0.8)
    lessons = bridge.get_relevant_lessons("shared crash", ["net"])
    assert len(lessons) == 1
    assert lessons[0]["solution"] == "fix socket"
