"""Tests for MemoryCompactor."""
from __future__ import annotations

from qa_framework.memory_compactor import MemoryCompactor, MemoryTier


class TestMemoryCompactor:
    def test_tier_promotion(self) -> None:
        mc = MemoryCompactor(db_path=":memory:")
        mc.add_memory("session_1", "user prefers concise responses", tier=MemoryTier.WORKING)
        # Promote to episodic
        mc.promote("session_1", "user prefers concise responses", MemoryTier.EPISODIC)
        results = mc.query("session_1", tier=MemoryTier.EPISODIC)
        assert len(results) == 1
        assert results[0]["content"] == "user prefers concise responses"

    def test_compaction_flushes_working_to_episodic(self) -> None:
        mc = MemoryCompactor(db_path=":memory:", working_buffer_size=2)
        mc.add_memory("s1", "fact 1", tier=MemoryTier.WORKING)
        mc.add_memory("s1", "fact 2", tier=MemoryTier.WORKING)
        # Buffer full → triggers compaction
        mc.add_memory("s1", "fact 3", tier=MemoryTier.WORKING)
        # Old facts should be in episodic now
        episodic = mc.query("s1", tier=MemoryTier.EPISODIC)
        assert len(episodic) >= 1

    def test_add_memory_dedup(self) -> None:
        mc = MemoryCompactor(db_path=":memory:")
        id1 = mc.add_memory("s1", "duplicate fact", tier=MemoryTier.WORKING)
        id2 = mc.add_memory("s1", "duplicate fact", tier=MemoryTier.WORKING)
        assert id1 == id2

    def test_query_all_tiers(self) -> None:
        mc = MemoryCompactor(db_path=":memory:")
        mc.add_memory("s1", "working fact", tier=MemoryTier.WORKING)
        mc.promote("s1", "working fact", MemoryTier.EPISODIC)
        results = mc.query("s1")
        assert len(results) >= 1

    def test_get_working_set_respects_limit(self) -> None:
        mc = MemoryCompactor(db_path=":memory:", working_buffer_size=5)
        for i in range(10):
            mc.add_memory("s1", f"fact {i}", tier=MemoryTier.WORKING)
        working = mc.get_working_set("s1")
        assert len(working) <= 5

    def test_flush_episodic_to_semantic(self) -> None:
        mc = MemoryCompactor(db_path=":memory:")
        mc.add_memory("s1", "episodic fact", tier=MemoryTier.EPISODIC)
        moved = mc.flush_episodic_to_semantic("s1")
        assert moved == 1
        semantic = mc.query("s1", tier=MemoryTier.SEMANTIC)
        assert len(semantic) == 1

    def test_prune_archival_old_entries(self) -> None:
        mc = MemoryCompactor(db_path=":memory:")
        mc.add_memory("s1", "old fact", tier=MemoryTier.ARCHIVAL)
        # Update timestamp to old
        import time
        old_time = time.time() - (60 * 86400)  # 60 days old
        mc._conn.execute(
            "UPDATE memories SET created_at = ? WHERE session_id = ? AND tier = ?",
            (old_time, "s1", int(MemoryTier.ARCHIVAL)),
        )
        mc._conn.commit()
        pruned = mc.prune_archival(max_age_days=30)
        assert pruned == 1

    def test_stats_returns_tier_counts(self) -> None:
        mc = MemoryCompactor(db_path=":memory:")
        mc.add_memory("s1", "fact 1", tier=MemoryTier.WORKING)
        mc.add_memory("s1", "fact 2", tier=MemoryTier.EPISODIC)
        stats = mc.stats("s1")
        assert stats["WORKING"] == 1
        assert stats["EPISODIC"] == 1
        assert stats["SEMANTIC"] == 0
        assert stats["ARCHIVAL"] == 0

    def test_promote_only_upgrades_tier(self) -> None:
        mc = MemoryCompactor(db_path=":memory:")
        mc.add_memory("s1", "fact", tier=MemoryTier.EPISODIC)
        # Try to "promote" to lower tier (should fail)
        result = mc.promote("s1", "fact", MemoryTier.WORKING)
        assert not result
