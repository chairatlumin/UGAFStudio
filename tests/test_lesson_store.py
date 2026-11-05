"""Tests for LessonStore SQLite backend."""

from __future__ import annotations

from qa_framework.lesson_store import LessonStore


def test_lesson_store_records_and_retrieves() -> None:
    from qa_framework.lesson_store import LessonStore

    store = LessonStore(":memory:")
    lesson_id = store.add_lesson(
        agent_id="agent-1",
        pattern="UE5 crash on D3D12 E_INVALIDARG with ViGEmBus",
        solution="Use AttachThreadInput for input injection",
        tags=["ue5", "input", "d3d12"],
        confidence=0.95,
    )
    assert lesson_id > 0
    results = store.find_similar("UE5 crash ViGEmBus", limit=5)
    assert len(results) == 1
    assert results[0]["pattern"] == "UE5 crash on D3D12 E_INVALIDARG with ViGEmBus"
    store.close()


def test_find_similar_prefers_best_match() -> None:
    store = LessonStore(":memory:")
    store.add_lesson("a1", "postgres connection timeout retry", "increase pool size", ["db"], 0.8)
    best_id = store.add_lesson(
        "a1", "UE5 crash ViGEmBus input", "Use AttachThreadInput", ["ue5"], 0.9
    )
    results = store.find_similar("UE5 crash ViGEmBus", limit=5)
    assert len(results) >= 1
    assert results[0]["id"] == best_id
    store.close()


def test_find_similar_returns_empty_without_overlap() -> None:
    store = LessonStore(":memory:")
    store.add_lesson("a1", "postgres connection timeout", "increase pool size", ["db"], 0.8)
    assert store.find_similar("completely unrelated zebra foxtrot", limit=5) == []
    store.close()


def test_record_hit_increments_count() -> None:
    store = LessonStore(":memory:")
    lesson_id = store.add_lesson("a1", "flaky QA gate retry", "rerun once", ["qa"], 0.7)
    store.record_hit(lesson_id)
    store.record_hit(lesson_id)
    lesson = store.get_lesson(lesson_id)
    assert lesson is not None
    assert lesson["hit_count"] == 2
    store.close()


def test_get_stats_reports_totals() -> None:
    store = LessonStore(":memory:")
    lid = store.add_lesson("a1", "pattern one alpha", "fix one", ["t1"], 0.9)
    store.add_lesson("a2", "pattern two beta", "fix two", ["t2"], 0.8)
    store.record_hit(lid)
    stats = store.get_stats()
    assert stats["total_lessons"] == 2
    assert stats["total_hits"] == 1
    store.close()
