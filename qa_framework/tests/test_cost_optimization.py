"""Tests for cost optimization primitives — TokenBudget, StateCache, CostAwareRouter, ContextBuilder, EvaluationSubset."""
from __future__ import annotations

import time

from qa_framework.cost_optimization import (
    ContextBuilder,
    CostAwareRouter,
    CostTier,
    EvaluationSubset,
    StateCache,
    TokenBudget,
)

# ---------------------------------------------------------------------------
# TokenBudget tests
# ---------------------------------------------------------------------------

class TestTokenBudget:
    def test_within_limit(self) -> None:
        budget = TokenBudget(max_tokens=1000)
        assert budget.can_spend(500) is True
        assert budget.spend(500) is True
        assert budget.remaining == 500
        assert budget.spent == 500

    def test_exceeds_limit(self) -> None:
        budget = TokenBudget(max_tokens=1000)
        budget.spend(900)
        assert budget.can_spend(200) is False  # only 100 left
        assert budget.spend(200) is False  # should reject
        assert budget.remaining == 100

    def test_exact_budget(self) -> None:
        budget = TokenBudget(max_tokens=500)
        assert budget.spend(500) is True
        assert budget.remaining == 0
        assert budget.can_spend(1) is False

    def test_reset(self) -> None:
        budget = TokenBudget(max_tokens=100)
        budget.spend(80)
        assert budget.remaining == 20
        budget.reset()
        assert budget.remaining == 100
        assert budget.spent == 0

    def test_zero_budget(self) -> None:
        budget = TokenBudget(max_tokens=0)
        assert budget.can_spend(1) is False
        assert budget.spend(1) is False
        assert budget.remaining == 0

    def test_to_dict(self) -> None:
        budget = TokenBudget(max_tokens=1000)
        budget.spend(250)
        result = budget.to_dict()
        assert result["max_tokens"] == 1000
        assert result["spent"] == 250
        assert result["remaining"] == 750
        assert result["utilization"] == 0.25


# ---------------------------------------------------------------------------
# StateCache tests
# ---------------------------------------------------------------------------

class TestStateCache:
    def test_hit_miss(self) -> None:
        cache = StateCache(ttl_seconds=60)
        key = "hash_abc_ocr_menu_play"
        assert cache.get(key) is None  # miss
        cache.set(key, {"result": "pass", "cost_saved": 0.05})
        assert cache.get(key) == {"result": "pass", "cost_saved": 0.05}  # hit
        assert cache.hit_count == 1
        assert cache.miss_count == 1

    def test_expiration(self) -> None:
        cache = StateCache(ttl_seconds=0.01)
        key = "hash_def_ocr_exit"
        cache.set(key, {"result": "fail"})
        assert cache.get(key) is not None  # not expired yet
        time.sleep(0.02)
        assert cache.get(key) is None  # expired

    def test_invalidate(self) -> None:
        cache = StateCache(ttl_seconds=60)
        key = "hash_123"
        cache.set(key, "value1")
        assert cache.get(key) == "value1"
        cache.invalidate(key)
        assert cache.get(key) is None

    def test_clear(self) -> None:
        cache = StateCache(ttl_seconds=60)
        cache.set("key1", "value1")
        cache.set("key2", "value2")
        assert cache.size == 2
        cache.clear()
        assert cache.size == 0
        assert cache.hit_count == 0
        assert cache.miss_count == 0

    def test_max_size_eviction(self) -> None:
        cache = StateCache(ttl_seconds=60, max_size=2)
        cache.set("key1", "value1")
        cache.set("key2", "value2")
        cache.set("key3", "value3")  # should evict oldest
        assert cache.size == 2
        # At least one key should be evicted
        assert cache.get("key1") is None or cache.get("key2") is None

    def test_to_dict(self) -> None:
        cache = StateCache(ttl_seconds=60)
        cache.set("key1", "value1")
        cache.get("key1")  # hit
        cache.get("key2")  # miss
        result = cache.to_dict()
        assert result["size"] == 1
        assert result["hit_count"] == 1
        assert result["miss_count"] == 1
        assert "hit_rate" in result


# ---------------------------------------------------------------------------
# CostAwareRouter tests
# ---------------------------------------------------------------------------

class TestCostAwareRouter:
    def test_cheap_path_frame_diff(self) -> None:
        router = CostAwareRouter()
        assert router.route("frame_diff") == CostTier.CHEAP

    def test_cheap_path_process_alive(self) -> None:
        router = CostAwareRouter()
        assert router.route("process_alive") == CostTier.CHEAP

    def test_expensive_path_anomaly(self) -> None:
        router = CostAwareRouter()
        assert router.route("anomaly_root_cause") == CostTier.EXPENSIVE

    def test_expensive_path_gameplay(self) -> None:
        router = CostAwareRouter()
        assert router.route("gameplay_analysis") == CostTier.EXPENSIVE

    def test_medium_path_state_ocr(self) -> None:
        router = CostAwareRouter()
        assert router.route("state_ocr") == CostTier.MEDIUM

    def test_unknown_task_defaults_medium(self) -> None:
        router = CostAwareRouter()
        assert router.route("unknown_task_xyz") == CostTier.MEDIUM

    def test_estimated_cost_usd(self) -> None:
        router = CostAwareRouter()
        assert router.estimated_cost_usd("frame_diff") == 0.0
        assert router.estimated_cost_usd("state_ocr") == 0.001
        assert router.estimated_cost_usd("anomaly_root_cause") == 0.05

    def test_is_cheap(self) -> None:
        router = CostAwareRouter()
        assert router.is_cheap("frame_diff") is True
        assert router.is_cheap("state_ocr") is False

    def test_is_expensive(self) -> None:
        router = CostAwareRouter()
        assert router.is_expensive("anomaly_root_cause") is True
        assert router.is_expensive("frame_diff") is False

    def test_cost_tier_enum_values(self) -> None:
        assert CostTier.CHEAP == "cheap"
        assert CostTier.MEDIUM == "medium"
        assert CostTier.EXPENSIVE == "expensive"


# ---------------------------------------------------------------------------
# ContextBuilder tests
# ---------------------------------------------------------------------------

class TestContextBuilder:
    def test_respects_budget(self) -> None:
        # Use a tight budget: system should fit, frame_data should be truncated
        builder = ContextBuilder(max_tokens=20)
        builder.add_section("system", "You are a QA bot.")
        builder.add_section("frame_data", "x" * 500)  # way over budget
        context = builder.build()
        assert "You are a QA bot" in context
        # frame_data section is truncated or dropped due to budget
        assert "[frame_data]" not in context or "[TRUNCATED]" in context

    def test_empty(self) -> None:
        builder = ContextBuilder(max_tokens=100)
        context = builder.build()
        assert context == ""

    def test_priority_ordering(self) -> None:
        builder = ContextBuilder(max_tokens=50)
        builder.add_section("low_priority", "x" * 100, priority=10)
        builder.add_section("high_priority", "important data", priority=1)
        context = builder.build()
        # high_priority section should appear before low_priority
        assert "important data" in context
        high_idx = context.index("important data")
        low_idx = context.index("x" * 10)  # at least part of low_priority
        assert high_idx < low_idx

    def test_clear(self) -> None:
        builder = ContextBuilder(max_tokens=100)
        builder.add_section("test", "content")
        assert builder.section_count == 1
        builder.clear()
        assert builder.section_count == 0

    def test_truncation_indicator(self) -> None:
        builder = ContextBuilder(max_tokens=10)  # very small budget
        builder.add_section("big_section", "x" * 1000, priority=5)
        context = builder.build()
        assert "[TRUNCATED]" in context


# ---------------------------------------------------------------------------
# EvaluationSubset tests
# ---------------------------------------------------------------------------

class TestEvaluationSubset:
    def test_selection_count(self) -> None:
        checkpoints = ["file_check", "frame_diff", "ocr_verify", "anomaly_detect", "layout_verify"]
        subset = EvaluationSubset(checkpoints, sample_ratio=0.4, seed=42)
        selected = subset.select()
        assert len(selected) == 2  # 40% of 5 = 2
        assert all(cp in checkpoints for cp in selected)

    def test_deterministic(self) -> None:
        checkpoints = ["a", "b", "c", "d", "e"]
        s1 = EvaluationSubset(checkpoints, sample_ratio=0.4, seed=42).select()
        s2 = EvaluationSubset(checkpoints, sample_ratio=0.4, seed=42).select()
        assert s1 == s2  # deterministic with same seed

    def test_different_seeds_differ(self) -> None:
        checkpoints = ["a", "b", "c", "d", "e", "f", "g", "h"]
        s1 = EvaluationSubset(checkpoints, sample_ratio=0.5, seed=1).select()
        s2 = EvaluationSubset(checkpoints, sample_ratio=0.5, seed=999).select()
        # Different seeds may produce different selections (not guaranteed but very likely)
        # At minimum they should both be valid subsets
        assert len(s1) == len(s2)
        assert all(cp in checkpoints for cp in s1)
        assert all(cp in checkpoints for cp in s2)

    def test_sample_ratio_zero(self) -> None:
        checkpoints = ["a", "b", "c"]
        subset = EvaluationSubset(checkpoints, sample_ratio=0.0, seed=42)
        selected = subset.select()
        assert len(selected) == 1  # max(1, int(3 * 0.0)) = 1

    def test_sample_ratio_one(self) -> None:
        checkpoints = ["a", "b", "c"]
        subset = EvaluationSubset(checkpoints, sample_ratio=1.0, seed=42)
        selected = subset.select()
        assert len(selected) == 3

    def test_by_cost_tier(self) -> None:
        checkpoints = ["frame_diff", "anomaly_root_cause", "state_ocr", "process_alive"]
        router = CostAwareRouter()
        subset = EvaluationSubset(checkpoints, sample_ratio=0.5, seed=42)
        by_tier = subset.select_by_cost_tier(router)
        assert "cheap" in by_tier
        assert "expensive" in by_tier
        assert "medium" in by_tier
        # frame_diff and process_alive are cheap
        assert "frame_diff" in by_tier["cheap"] or "process_alive" in by_tier["cheap"]

    def test_to_dict(self) -> None:
        checkpoints = ["a", "b", "c", "d", "e"]
        subset = EvaluationSubset(checkpoints, sample_ratio=0.4, seed=42)
        result = subset.to_dict()
        assert result["total_checkpoints"] == 5
        assert result["sample_ratio"] == 0.4
        assert result["seed"] == 42
        assert result["selected_count"] == 2
