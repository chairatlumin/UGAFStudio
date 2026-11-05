"""Tests for memory curation primitives."""
from __future__ import annotations

import time


class TestKnownStateGraph:
    """Tests for KnownStateGraph — O(1) state recognition."""

    def test_add_and_lookup(self) -> None:
        from qa_framework.memory_curator import KnownStateGraph

        graph = KnownStateGraph()
        graph.add_state("hash_abc_ocr_menu_play", {"result": "pass", "cost_saved": 0.05})

        result = graph.lookup("hash_abc_ocr_menu_play")
        assert result is not None
        assert result["result"] == "pass"
        assert result["cost_saved"] == 0.05

    def test_lookup_unknown(self) -> None:
        from qa_framework.memory_curator import KnownStateGraph

        graph = KnownStateGraph()
        assert graph.lookup("nonexistent_key") is None

    def test_lookup_similar_within_threshold(self) -> None:
        from qa_framework.memory_curator import KnownStateGraph

        graph = KnownStateGraph(similarity_threshold=0.8)
        graph.add_state("hash_abc_ocr_menu_play", {"result": "pass"})

        # Shares 4 of 5 tokens with itself -> Jaccard ≈ 0.8
        similar = graph.lookup_similar("hash_abc_ocr_menu", threshold=0.8)
        assert similar is not None
        assert similar["result"] == "pass"

    def test_lookup_similar_below_threshold(self) -> None:
        from qa_framework.memory_curator import KnownStateGraph

        graph = KnownStateGraph(similarity_threshold=0.9)
        graph.add_state("hash_abc_ocr_menu_play", {"result": "pass"})

        # Only 2 of 6 tokens match -> Jaccard ≈ 0.33
        assert graph.lookup_similar("hash_xyz_different", threshold=0.9) is None

    def test_lookup_similar_no_match(self) -> None:
        from qa_framework.memory_curator import KnownStateGraph

        graph = KnownStateGraph(similarity_threshold=0.9)
        graph.add_state("hash_abc_ocr_menu", {"result": "pass"})

        # Very different key
        assert graph.lookup_similar("completely_different_key", threshold=0.9) is None

    def test_stats(self) -> None:
        from qa_framework.memory_curator import KnownStateGraph

        graph = KnownStateGraph()
        graph.add_state("key_a", {"result": "pass"})
        graph.add_state("key_b", {"result": "fail"})

        # Access key_a twice
        graph.lookup("key_a")
        graph.lookup("key_a")

        stats = graph.stats()
        assert stats["total_states"] == 2
        assert stats["total_accesses"] == 2


class TestMemoryCurator:
    """Tests for MemoryCurator — async state consolidation."""

    def test_consolidation_basic(self) -> None:
        from qa_framework.cost_optimization import StateCache
        from qa_framework.memory_curator import MemoryCurator

        cache = StateCache(ttl_seconds=300)
        cache.set("hash_menu_play_ocr_start", {"result": "pass", "cost_saved": 0.05})
        cache.set("hash_menu_exit_ocr_quit", {"result": "pass", "cost_saved": 0.05})
        cache.set("hash_combat_ocr_fight", {"result": "fail", "cost_saved": 0.0})

        curator = MemoryCurator(cache)
        stats = curator.consolidate()

        assert stats["states_reviewed"] == 3
        assert stats["states_consolidated"] >= 2  # pass states consolidated
        assert stats["stale_evicted"] == 0  # nothing stale yet

    def test_stale_eviction(self) -> None:
        from qa_framework.cost_optimization import StateCache
        from qa_framework.memory_curator import MemoryCurator

        cache = StateCache(ttl_seconds=0.01)
        cache.set("stale_key_old", {"result": "pass"})
        time.sleep(0.02)

        curator = MemoryCurator(cache)
        stats = curator.consolidate()

        assert stats["stale_evicted"] >= 1

    def test_get_graph_stats(self) -> None:
        from qa_framework.cost_optimization import StateCache
        from qa_framework.memory_curator import MemoryCurator

        cache = StateCache(ttl_seconds=300)
        cache.set("hash_key_1", {"result": "pass"})

        curator = MemoryCurator(cache)
        curator.consolidate()

        graph_stats = curator.get_graph_stats()
        assert graph_stats["total_states"] >= 1


class TestSkillTracker:
    """Tests for SkillTracker — usage-based pruning."""

    def test_record_use(self) -> None:
        from qa_framework.memory_curator import SkillTracker

        tracker = SkillTracker()
        tracker.record_use("playbook-system")
        tracker.record_use("playbook-system")
        tracker.record_use("harness-layer")

        assert tracker.get_use_count("playbook-system") == 2
        assert tracker.get_use_count("harness-layer") == 1

    def test_get_use_count_unknown(self) -> None:
        from qa_framework.memory_curator import SkillTracker

        tracker = SkillTracker()
        assert tracker.get_use_count("nonexistent") == 0

    def test_prune_candidates(self) -> None:
        from qa_framework.memory_curator import SkillTracker

        tracker = SkillTracker(max_age_seconds=0.01)
        tracker.record_use("old-skill")
        time.sleep(0.02)
        tracker.record_use("new-skill")

        candidates = tracker.get_prune_candidates()
        assert "old-skill" in candidates
        assert "new-skill" not in candidates

    def test_stats(self) -> None:
        from qa_framework.memory_curator import SkillTracker

        tracker = SkillTracker()
        tracker.record_use("skill-a")
        tracker.record_use("skill-a")
        tracker.record_use("skill-b")

        stats = tracker.stats()
        assert stats["total_skills"] == 2
        assert stats["total_uses"] == 3


class TestFullPipeline:
    """Integration test — full consolidation pipeline."""

    def test_full_consolidation_pipeline(self) -> None:
        from qa_framework.cost_optimization import StateCache
        from qa_framework.memory_curator import KnownStateGraph, MemoryCurator

        cache = StateCache(ttl_seconds=300)
        graph = KnownStateGraph()
        curator = MemoryCurator(cache, known_graph=graph)

        cache.set("hash_menu_play_ocr_start", {"result": "pass", "cost_saved": 0.05})
        cache.set("hash_menu_exit_ocr_quit", {"result": "pass", "cost_saved": 0.05})
        cache.set("hash_combat_ocr_fight", {"result": "fail", "cost_saved": 0.0})

        stats = curator.consolidate()

        assert stats["states_reviewed"] == 3
        assert stats["states_consolidated"] >= 2

        result = graph.lookup("hash_menu_play_ocr_start")
        assert result is not None
        assert result["result"] == "pass"

        # Similar lookup with lower threshold
        similar = graph.lookup_similar("hash_menu_play_ocr_begin", threshold=0.5)
        assert similar is not None
