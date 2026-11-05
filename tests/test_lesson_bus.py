"""Tests for LessonBus pub/sub."""

from __future__ import annotations

from typing import Any

from qa_framework.lesson_bus import LessonBus
from qa_framework.lesson_store import LessonStore


def test_lesson_bus_subscribe_and_publish() -> None:
    from qa_framework.lesson_bus import LessonBus
    from qa_framework.lesson_store import LessonStore

    store = LessonStore(":memory:")
    bus = LessonBus(store)
    received: list[dict[str, Any]] = []
    bus.subscribe("agent-2", ["ue5", "input"], callback=lambda lesson: received.append(lesson))
    bus.publish(
        agent_id="agent-1",
        pattern="UE5 crash on D3D12 E_INVALIDARG",
        solution="Use AttachThreadInput",
        tags=["ue5", "input"],
        confidence=0.95,
    )
    assert len(received) == 1
    store.close()


def test_lesson_bus_publish_without_match_notifies_nobody() -> None:
    store = LessonStore(":memory:")
    bus = LessonBus(store)
    received: list[dict[str, Any]] = []
    bus.subscribe("agent-2", ["database"], callback=lambda lesson: received.append(lesson))
    lesson_id = bus.publish("agent-1", "UE5 crash input", "Use AttachThreadInput", ["ue5"], 0.9)
    assert lesson_id > 0
    assert received == []
    # Lesson is still stored even when nobody listens.
    assert len(store.find_similar("UE5 crash input", limit=5)) == 1
    store.close()


def test_lesson_bus_notifies_only_matching_subscribers() -> None:
    store = LessonStore(":memory:")
    bus = LessonBus(store)
    matched: list[dict[str, Any]] = []
    unmatched: list[dict[str, Any]] = []
    bus.subscribe("agent-2", ["ue5"], callback=lambda lesson: matched.append(lesson))
    bus.subscribe("agent-3", ["database"], callback=lambda lesson: unmatched.append(lesson))
    bus.publish("agent-1", "UE5 crash input", "Use AttachThreadInput", ["ue5"], 0.9)
    assert len(matched) == 1
    assert matched[0]["solution"] == "Use AttachThreadInput"
    assert unmatched == []
    store.close()
