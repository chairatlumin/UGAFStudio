"""Tests for memory_evaluator.py — MemoryEvaluator and ForgettingScheduler."""

import time

import pytest

from qa_framework.memory_evaluator import ForgettingScheduler, MemoryEvaluator
from qa_framework.telemetry import SpanHierarchy


@pytest.fixture
def evaluator(tmp_path):
    """Create MemoryEvaluator with temp db."""
    db_path = tmp_path / "test_memory_eval.db"
    return MemoryEvaluator(db_path=str(db_path))


@pytest.fixture
def scheduler(tmp_path):
    """Create ForgettingScheduler."""
    return ForgettingScheduler(max_age_seconds=3600)


class TestMemoryEvaluator:
    def test_record_decision_with_memory(self, evaluator):
        evaluator.record_decision("task-1", used_memory=True, outcome="pass")
        stats = evaluator.get_stats()
        assert stats["with_memory"]["count"] == 1
        assert stats["without_memory"]["count"] == 0
        assert stats["with_memory"]["success_rate"] == 1.0

    def test_record_decision_without_memory(self, evaluator):
        evaluator.record_decision("task-1", used_memory=False, outcome="fail")
        stats = evaluator.get_stats()
        assert stats["with_memory"]["count"] == 0
        assert stats["without_memory"]["count"] == 1
        assert stats["without_memory"]["success_rate"] == 0.0

    def test_record_decision_mixed(self, evaluator):
        evaluator.record_decision("t1", used_memory=True, outcome="pass")
        evaluator.record_decision("t2", used_memory=True, outcome="fail")
        evaluator.record_decision("t3", used_memory=False, outcome="fail")
        evaluator.record_decision("t4", used_memory=False, outcome="fail")
        stats = evaluator.get_stats()
        assert stats["with_memory"]["count"] == 2
        assert stats["with_memory"]["success_rate"] == 0.5
        assert stats["without_memory"]["count"] == 2
        assert stats["without_memory"]["success_rate"] == 0.0

    def test_get_precision_relevant(self, evaluator):
        evaluator.record_retrieval("task-1", retrieved=["fact_A"], relevant=["fact_A"], outcome="pass")
        assert evaluator.get_precision() == 1.0

    def test_get_precision_mixed(self, evaluator):
        evaluator.record_retrieval("task-1", retrieved=["fact_A"], relevant=["fact_A"], outcome="pass")
        evaluator.record_retrieval("task-2", retrieved=["fact_B"], relevant=["fact_A"], outcome="fail")
        assert evaluator.get_precision() == 0.5

    def test_get_precision_empty(self, evaluator):
        assert evaluator.get_precision() == 0.0


class TestForgettingScheduler:
    def test_no_entries(self, scheduler):
        assert scheduler.get_archive_candidates() == []

    def test_recent_access_not_archived(self, scheduler):
        scheduler.record_access("fact_A")
        assert "fact_A" not in scheduler.get_archive_candidates()

    def test_stale_entry_archived(self, scheduler):
        scheduler.record_access("fact_A")
        # Manually expire
        scheduler._access_times["fact_A"] = time.time() - 7200
        assert "fact_A" in scheduler.get_archive_candidates()

    def test_keep_forever(self, scheduler):
        scheduler.record_access("critical_fact")
        scheduler.set_keep_forever("critical_fact")
        scheduler._access_times["critical_fact"] = time.time() - 99999
        assert "critical_fact" not in scheduler.get_archive_candidates()

    def test_mixed_entries(self, scheduler):
        scheduler.record_access("recent")
        scheduler.record_access("stale")
        scheduler._access_times["stale"] = time.time() - 7200
        candidates = scheduler.get_archive_candidates()
        assert "recent" not in candidates
        assert "stale" in candidates


class TestSpanHierarchyIntegration:
    def test_memory_evaluator_emits_span(self, evaluator):
        h = SpanHierarchy(agent_name="test", trace_id="t1")
        evaluator.accept_span_hierarchy(h)
        evaluator.record_decision("task-1", used_memory=True, outcome="pass")
        assert h.total_spans == 1
        summary = h.finish()
        assert summary["total_spans"] == 1
