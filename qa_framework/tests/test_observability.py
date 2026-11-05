"""Tests for observability primitives in qa_framework.observability."""
from __future__ import annotations

import json
import os
import tempfile
import time

import pytest

from qa_framework.metrics import CostTracker
from qa_framework.observability import (
    CircuitBreaker,
    IdempotencyGuard,
    TraceExporter,
    TraceSpan,
)

# ---------------------------------------------------------------------------
# TraceSpan tests
# ---------------------------------------------------------------------------

class TestTraceSpan:
    def test_records_timing(self):
        with TraceSpan("test_op") as span:
            time.sleep(0.01)
        assert span.elapsed >= 0.01
        assert span.success is True
        assert span.name == "test_op"
        assert span.error == ""

    def test_records_exception(self):
        with pytest.raises(ValueError):
            with TraceSpan("failing_op") as span:
                raise ValueError("boom")
        assert span.success is False
        assert "boom" in span.error

    def test_metadata_preserved(self):
        with TraceSpan("meta_op", metadata={"app_id": 4077460, "phase": "launch"}) as span:
            pass
        assert span.metadata["app_id"] == 4077460
        assert span.metadata["phase"] == "launch"

    def test_to_dict_has_expected_keys(self):
        with TraceSpan("dict_op") as span:
            pass
        d = span.to_dict()
        assert "name" in d
        assert "elapsed_ms" in d
        assert "success" in d
        assert "error" in d
        assert "metadata" in d
        assert d["name"] == "dict_op"

    def test_elapsed_non_negative(self):
        with TraceSpan("instant") as span:
            pass
        assert span.elapsed >= 0.0


# ---------------------------------------------------------------------------
# CircuitBreaker tests
# ---------------------------------------------------------------------------

class TestCircuitBreaker:
    def test_starts_closed(self):
        cb = CircuitBreaker(max_failures=3)
        assert cb.is_open is False

    def test_opens_after_max_failures(self):
        cb = CircuitBreaker(max_failures=3)
        cb.record_failure()
        assert cb.is_open is False
        cb.record_failure()
        assert cb.is_open is False
        cb.record_failure()
        assert cb.is_open is True

    def test_success_resets_failure_count(self):
        cb = CircuitBreaker(max_failures=5)
        cb.record_failure()
        cb.record_failure()
        cb.record_success()
        assert cb.failure_count == 0
        assert cb.success_count == 1
        assert cb.is_open is False

    def test_reset_clears_all(self):
        cb = CircuitBreaker(max_failures=3)
        for _ in range(3):
            cb.record_failure()
        assert cb.is_open is True
        cb.reset()
        assert cb.is_open is False
        assert cb.failure_count == 0
        assert cb.success_count == 0

    def test_custom_max_failures(self):
        cb = CircuitBreaker(max_failures=1)
        cb.record_failure()
        assert cb.is_open is True


# ---------------------------------------------------------------------------
# IdempotencyGuard tests
# ---------------------------------------------------------------------------

class TestIdempotencyGuard:
    def test_acquire_release_cycle(self):
        guard = IdempotencyGuard()
        assert guard.acquire("launch_123") is True
        assert guard.active_count == 1
        assert guard.acquire("launch_123") is False
        guard.release("launch_123")
        assert guard.active_count == 0
        assert guard.acquire("launch_123") is True

    def test_different_keys_independent(self):
        guard = IdempotencyGuard()
        assert guard.acquire("launch_A") is True
        assert guard.acquire("launch_B") is True
        assert guard.active_count == 2
        guard.release("launch_A")
        assert guard.active_count == 1

    def test_release_unknown_key_no_error(self):
        guard = IdempotencyGuard()
        guard.release("nonexistent")  # should not raise

    def test_acquire_after_release_allows_reentry(self):
        guard = IdempotencyGuard()
        guard.acquire("op1")
        guard.release("op1")
        assert guard.acquire("op1") is True


# ---------------------------------------------------------------------------
# TraceExporter tests
# ---------------------------------------------------------------------------

class TestTraceExporter:
    def test_export_writes_jsonl(self):
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            path = f.name
        try:
            exporter = TraceExporter(path)
            spans = []
            for i in range(3):
                with TraceSpan(f"op_{i}", metadata={"idx": i}) as span:
                    pass
                spans.append(span)
            exporter.export(spans)
            with open(path, encoding="utf-8") as f:
                lines = f.readlines()
            assert len(lines) == 3
            first = json.loads(lines[0])
            assert first["name"] == "op_0"
            assert first["success"] is True
            assert first["metadata"]["idx"] == 0
        finally:
            os.unlink(path)

    def test_export_empty_list(self):
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            path = f.name
        try:
            exporter = TraceExporter(path)
            exporter.export([])
            with open(path, encoding="utf-8") as f:
                content = f.read()
            assert content == ""
        finally:
            os.unlink(path)


# ---------------------------------------------------------------------------
# CostTracker per-decision tests
# ---------------------------------------------------------------------------

class TestCostTrackerPerDecision:
    def test_record_checkpoint_cost(self):
        ct = CostTracker()
        ct.record_checkpoint_cost("file_check", tokens=100, cost_usd=0.001)
        ct.record_checkpoint_cost("ocr_verify", tokens=500, cost_usd=0.005)
        summary = ct.summary()
        assert "decisions" in summary
        assert summary["decisions"]["file_check"]["tokens"] == 100
        assert summary["decisions"]["ocr_verify"]["cost_usd"] == 0.005

    def test_record_checkpoint_cost_accumulates(self):
        ct = CostTracker()
        ct.record_checkpoint_cost("cp1", tokens=100, cost_usd=0.001)
        ct.record_checkpoint_cost("cp1", tokens=200, cost_usd=0.002)
        summary = ct.summary()
        assert summary["decisions"]["cp1"]["tokens"] == 300
        assert summary["decisions"]["cp1"]["cost_usd"] == 0.003
        assert summary["decisions"]["cp1"]["count"] == 2

    def test_summary_has_expected_keys(self):
        ct = CostTracker()
        ct.record_checkpoint_cost("test", tokens=100, cost_usd=0.001)
        summary = ct.summary()
        assert "total_tokens" in summary
        assert "total_cost_usd" in summary
        assert "decisions" in summary
        assert "entries" in summary

    def test_cost_per_correct(self):
        ct = CostTracker()
        ct.record_checkpoint_cost("good", tokens=100, cost_usd=0.001)
        summary = ct.summary()
        assert summary["cost_per_correct_usd"] > 0.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
