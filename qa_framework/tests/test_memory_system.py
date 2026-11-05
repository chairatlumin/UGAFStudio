"""Comprehensive tests for the three-tier memory system."""

from __future__ import annotations

import threading
from pathlib import Path

import pytest

from qa_framework.memory import (
    EpisodicStore,
    MemoryRouter,
    ProceduralStore,
    SemanticStore,
)


@pytest.fixture
def tmp_db(tmp_path: Path) -> Path:
    return tmp_path / "test_memory.db"


class TestEpisodicStore:
    def test_record_and_get_recent(self, tmp_db: Path) -> None:
        store = EpisodicStore(str(tmp_db))
        sid = "session-1"
        store.record(sid, "state_a", "jump", "success", 1.0)
        store.record(sid, "state_b", "attack", "hit", 0.5)
        recent = store.get_recent(10)
        assert len(recent) == 2
        assert recent[0]["action"] == "attack"  # most recent first
        assert recent[1]["action"] == "jump"

    def test_get_by_action(self, tmp_db: Path) -> None:
        store = EpisodicStore(str(tmp_db))
        store.record("s1", "a", "jump", "ok", 1.0)
        store.record("s1", "b", "attack", "hit", 0.5)
        store.record("s1", "c", "jump", "fail", -0.5)
        results = store.get_by_action("jump")
        assert len(results) == 2
        assert all(r["action"] == "jump" for r in results)

    def test_get_by_state(self, tmp_db: Path) -> None:
        store = EpisodicStore(str(tmp_db))
        store.record("s1", "state_x", "move", "ok", 0.1)
        store.record("s1", "state_x", "jump", "ok", 0.2)
        store.record("s1", "state_y", "move", "ok", 0.1)
        results = store.get_by_state("state_x")
        assert len(results) == 2
        assert all(r["state_hash"] == "state_x" for r in results)

    def test_prune(self, tmp_db: Path) -> None:
        store = EpisodicStore(str(tmp_db))
        # Insert records across multiple sessions
        for i in range(10):
            store.record(f"session-{i}", f"state-{i}", "action", "outcome", 0.0)
        # Keep only the last 3 sessions
        deleted = store.prune(older_than_sessions=3)
        assert deleted == 7
        remaining = store.get_recent(100)
        assert len(remaining) == 3
        # Verify the 3 most recent sessions remain
        sids = {r["session_id"] for r in remaining}
        assert sids == {"session-7", "session-8", "session-9"}

    def test_count_sessions(self, tmp_db: Path) -> None:
        store = EpisodicStore(str(tmp_db))
        store.record("s1", "a", "x", "y", 0.0)
        store.record("s2", "a", "x", "y", 0.0)
        store.record("s1", "b", "x", "y", 0.0)
        assert store.count_sessions() == 2

    def test_get_session_records(self, tmp_db: Path) -> None:
        store = EpisodicStore(str(tmp_db))
        store.record("s1", "a", "jump", "ok", 1.0)
        store.record("s2", "b", "run", "ok", 0.5)
        store.record("s1", "c", "attack", "hit", 0.8)
        records = store.get_session_records("s1")
        assert len(records) == 2
        assert records[0]["action"] == "jump"
        assert records[1]["action"] == "attack"


class TestSemanticStore:
    def test_upsert_new_fact(self, tmp_db: Path) -> None:
        store = SemanticStore(str(tmp_db))
        store.upsert_fact("boss_health", "100", 0.6)
        facts = store.query_facts("boss_health")
        assert len(facts) == 1
        assert facts[0]["value"] == "100"
        assert facts[0]["confidence"] == pytest.approx(0.6)

    def test_upsert_existing_fact_increments(self, tmp_db: Path) -> None:
        store = SemanticStore(str(tmp_db))
        store.upsert_fact("enemy_count", "5", 0.5)
        store.upsert_fact("enemy_count", "5", 0.5)
        facts = store.query_facts("enemy_count")
        assert len(facts) == 1
        assert facts[0]["confidence"] == pytest.approx(0.6)  # 0.5 + 0.1
        assert facts[0]["corroborations"] == 1

    def test_corroborate(self, tmp_db: Path) -> None:
        store = SemanticStore(str(tmp_db))
        store.upsert_fact("item_location", "chest_42", 0.5)
        store.corroborate("item_location", delta=0.2)
        facts = store.query_facts("item_location")
        assert facts[0]["confidence"] == pytest.approx(0.7)

    def test_contradict(self, tmp_db: Path) -> None:
        store = SemanticStore(str(tmp_db))
        store.upsert_fact("safe_path", "left", 0.8)
        store.contradict("safe_path")
        facts = store.query_facts("safe_path")
        assert facts[0]["confidence"] == pytest.approx(0.6)  # 0.8 - 0.2
        assert facts[0]["contradicted"] == 1

    def test_query_facts_pattern(self, tmp_db: Path) -> None:
        store = SemanticStore(str(tmp_db))
        store.upsert_fact("level1_enemy", "3", 0.5)
        store.upsert_fact("level1_boss", "1", 0.7)
        store.upsert_fact("level2_enemy", "5", 0.6)
        results = store.query_facts("level1")
        assert len(results) == 2

    def test_consolidate_from_episodic(self, tmp_db: Path) -> None:
        episodic = EpisodicStore(str(tmp_db))
        semantic = SemanticStore(str(tmp_db))
        # Record distinct interactions in session
        episodic.record("s1", "state_a", "jump", "success", 1.0)
        episodic.record("s1", "state_b", "attack", "hit", 0.5)
        episodic.record("s1", "state_a", "jump", "fail", -0.1)  # duplicate (state_hash, action)
        count = semantic.consolidate_from_episodic(episodic, "s1")
        assert count == 2  # 2 unique (state_hash, action) pairs
        facts = semantic.get_all_facts()
        assert len(facts) == 2

    def test_confidence_cap(self, tmp_db: Path) -> None:
        store = SemanticStore(str(tmp_db))
        store.upsert_fact("test_key", "val", 1.0)
        store.corroborate("test_key", delta=0.5)
        facts = store.query_facts("test_key")
        assert facts[0]["confidence"] <= 1.0


class TestProceduralStore:
    def test_store_and_find_skill(self, tmp_db: Path) -> None:
        store = ProceduralStore(str(tmp_db))
        store.store_skill(
            "boss_phase2",
            {"phase": "2", "boss": "dragon"},
            ["dodge_left", "dodge_left", "attack"],
            "boss_staggered",
        )
        matches = store.find_matching_skills("phase=2 boss=dragon")
        assert len(matches) == 1
        assert matches[0]["name"] == "boss_phase2"
        assert matches[0]["action_sequence"] == ["dodge_left", "dodge_left", "attack"]

    def test_find_skills_no_match(self, tmp_db: Path) -> None:
        store = ProceduralStore(str(tmp_db))
        store.store_skill(
            "level1_pattern",
            {"level": "1"},
            ["move_right"],
            "progress",
        )
        matches = store.find_matching_skills("level=2")
        assert len(matches) == 0

    def test_record_result(self, tmp_db: Path) -> None:
        store = ProceduralStore(str(tmp_db))
        sid = store.store_skill(
            "test_skill",
            {"state": "a"},
            ["action1"],
            "outcome1",
        )
        store.record_result(sid, True)
        store.record_result(sid, True)
        store.record_result(sid, False)
        skill = store.get_skill_by_id(sid)
        assert skill is not None
        assert skill["success_count"] == 2
        assert skill["fail_count"] == 1

    def test_get_top_skills(self, tmp_db: Path) -> None:
        store = ProceduralStore(str(tmp_db))
        s1 = store.store_skill("skill1", {"k": "v"}, ["a"], "o")
        s2 = store.store_skill("skill2", {"k": "v"}, ["b"], "o")
        store.record_result(s1, True)
        store.record_result(s1, True)
        store.record_result(s2, True)
        store.record_result(s2, False)
        store.record_result(s2, False)
        top = store.get_top_skills(5)
        assert top[0]["id"] == s1
        assert top[0]["net_success"] == 2

    def test_action_filter(self, tmp_db: Path) -> None:
        store = ProceduralStore(str(tmp_db))
        store.store_skill(
            "jump_attack",
            {"ground": "true"},
            ["jump", "attack"],
            "air_combo",
        )
        matches = store.find_matching_skills("ground=true", available_actions=["jump"])
        assert len(matches) == 0  # attack not in available_actions
        matches = store.find_matching_skills(
            "ground=true", available_actions=["jump", "attack"]
        )
        assert len(matches) == 1


class TestMemoryRouter:
    def test_record_and_query_what_happened(self, tmp_db: Path) -> None:
        router = MemoryRouter(str(tmp_db))
        router.record("s1", "state_a", "jump", "ok", 1.0)
        router.record("s1", "state_b", "attack", "hit", 0.5)
        results = router.query("what_happened", n=10)
        assert len(results) == 2
        assert all(r["_tier"] == "episodic" for r in results)

    def test_query_what_is_known(self, tmp_db: Path) -> None:
        router = MemoryRouter(str(tmp_db))
        router.semantic.upsert_fact("boss_weakpoint", "head", 0.7)
        results = router.query("what_is_known", key_pattern="boss")
        assert len(results) == 1
        assert results[0]["_tier"] == "semantic"
        assert results[0]["key"] == "boss_weakpoint"

    def test_query_how_to(self, tmp_db: Path) -> None:
        router = MemoryRouter(str(tmp_db))
        router.procedural.store_skill(
            "defeat_guard",
            {"enemy": "guard", "phase": "1"},
            ["parry", "riposte"],
            "enemy_down",
        )
        results = router.query("how_to", state_hash="enemy=guard phase=1")
        assert len(results) == 1
        assert results[0]["_tier"] == "procedural"

    def test_query_all(self, tmp_db: Path) -> None:
        router = MemoryRouter(str(tmp_db))
        router.record("s1", "st", "act", "out", 1.0)
        router.semantic.upsert_fact("fact_key", "fact_val", 0.6)
        # "all" query routes params to every tier; use n for episodic, key_pattern for semantic
        results = router.query("all", n=5, key_pattern="fact")
        tiers = {r["_tier"] for r in results}
        assert "episodic" in tiers
        assert "semantic" in tiers

    def test_consolidate(self, tmp_db: Path) -> None:
        router = MemoryRouter(str(tmp_db))
        router.record("s1", "state_x", "jump", "ok", 1.0)
        router.record("s1", "state_y", "run", "ok", 0.5)
        count = router.consolidate("s1")
        assert count == 2
        facts = router.semantic.get_all_facts()
        assert len(facts) == 2

    def test_summarize_session(self, tmp_db: Path) -> None:
        router = MemoryRouter(str(tmp_db))
        router.record("s1", "state_a", "jump", "ok", 1.0)
        router.record("s1", "state_b", "attack", "hit", 0.5)
        router.procedural.store_skill("demo", {"a": "b"}, ["x"], "y")
        summary = router.summarize_session("s1")
        assert summary["session_id"] == "s1"
        assert summary["total_actions"] == 2
        assert summary["unique_states"] == 2
        assert summary["facts_learned"] == 2

    def test_prune(self, tmp_db: Path) -> None:
        router = MemoryRouter(str(tmp_db))
        for i in range(10):
            router.record(f"session-{i}", f"state-{i}", "a", "o", 0.0)
        deleted = router.prune(older_than_sessions=3)
        assert deleted == 7


class TestThreadSafety:
    def test_concurrent_records(self, tmp_db: Path) -> None:
        store = EpisodicStore(str(tmp_db))
        errors: list[str] = []

        def worker(thread_id: int) -> None:
            try:
                for i in range(20):
                    store.record(
                        f"thread-{thread_id}",
                        f"state-{i}",
                        f"action-{i}",
                        "ok",
                        1.0,
                    )
            except Exception as e:
                errors.append(str(e))

        t1 = threading.Thread(target=worker, args=(1,))
        t2 = threading.Thread(target=worker, args=(2,))
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        assert not errors
        assert store.count_sessions() == 2
        assert len(store.get_recent(100)) == 40
