from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from qa_framework.gameplay_agent.skill_cache import SkillCache, _visual_hash, signature
from qa_framework.gameplay_agent.vlm_agent import VLMAgent


def test_signature_sorts_and_lowercases() -> None:
    """signature() sorts words, lowercases, and joins with '|'."""
    words = [{"text": "Banana"}, {"text": "apple"}, {"text": "Cherry"}]
    sig = signature(words)
    assert sig == "apple|banana|cherry"


def test_signature_ignores_duplicates() -> None:
    words = [{"text": "HP"}, {"text": "hp"}, {"text": "Hp"}]
    sig = signature(words)
    assert sig == "hp"


def test_signature_ignores_empty_text() -> None:
    words = [{"text": ""}, {"text": "  "}, {"text": "ok"}]
    sig = signature(words)
    assert sig == "ok"


def test_signature_with_frame_includes_visual_hash() -> None:
    """signature(frame=...) appends a 32-char hex visual hash after '| '|'."""
    words = [{"text": "hello"}]
    frame = np.random.randint(0, 256, (64, 64, 3), dtype=np.uint8)
    sig = signature(words, frame=frame)
    parts = sig.split("|")
    assert parts[0] == "hello"
    assert len(parts) == 2
    assert len(parts[1]) == 32
    assert all(c in "0123456789abcdef" for c in parts[1])


def test_visual_hash_differs_for_different_frames() -> None:
    frame_a = np.zeros((64, 64, 3), dtype=np.uint8)
    frame_b = np.full((64, 64, 3), 255, dtype=np.uint8)
    assert _visual_hash(frame_a) != _visual_hash(frame_b)


def test_visual_hash_same_for_same_frame() -> None:
    frame = np.random.randint(0, 256, (64, 64, 3), dtype=np.uint8)
    assert _visual_hash(frame) == _visual_hash(frame)


def test_combined_signature_stable_ordering() -> None:
    """Same words + same frame produce identical signature regardless of call order."""
    words = [{"text": "beta"}, {"text": "alpha"}]
    frame = np.ones((32, 32, 3), dtype=np.uint8) * 128
    sig1 = signature(words, frame=frame)
    sig2 = signature(list(reversed(words)), frame=frame)
    assert sig1 == sig2


def test_signature_without_frame_ocr_only() -> None:
    """Without frame, signature is pure OCR words (backward compatible)."""
    words = [{"text": "foo"}, {"text": "bar"}]
    sig = signature(words)
    assert sig == "bar|foo"


def test_put_get_roundtrip(tmp_path: Path) -> None:
    cache = SkillCache(path=tmp_path / "skills.json")
    cache.put("foo|bar", {"action": "key_press", "params": {"key": "w"}})
    result = cache.get("foo|bar")
    assert result is not None
    assert result["action"] == "key_press"
    assert result["params"] == {"key": "w"}


def test_get_miss_returns_none(tmp_path: Path) -> None:
    cache = SkillCache(path=tmp_path / "skills.json")
    assert cache.get("missing") is None


def test_persistence_to_disk(tmp_path: Path) -> None:
    path = tmp_path / "skills.json"
    cache = SkillCache(path=path)
    cache.put("a|b", {"action": "click", "params": {}})
    # Load a new instance from the same file
    cache2 = SkillCache(path=path)
    result = cache2.get("a|b")
    assert result is not None
    assert result["action"] == "click"


def test_fifo_eviction(tmp_path: Path) -> None:
    cache = SkillCache(path=tmp_path / "skills.json")
    # Put 201 entries
    for i in range(201):
        cache.put(f"sig{i}", {"action": f"act{i}", "params": {}})
    # First entry should be evicted
    assert cache.get("sig0") is None
    # Last entry should exist
    assert cache.get("sig200") is not None


def test_vlm_agent_cache_hit_skips_backend(tmp_path: Path) -> None:
    """When cache has the signature, VLMAgent returns cached action without calling backend."""
    call_count = 0

    class CountingBackend:
        def complete(self, prompt: str, image: np.ndarray) -> str:
            nonlocal call_count
            call_count += 1
            return json.dumps({"action": "click", "params": {"button": "left"}})

    cache = SkillCache.__new__(SkillCache)
    cache._data = {}
    cache._path = tmp_path / "skills.json"
    cache._outcomes = {}
    cache.put("hello|world", {"action": "key_press", "params": {"key": "space"}})
    cache.record_outcome("hello|world", success=True)

    agent = VLMAgent(
        backend=CountingBackend(),
        allowed_actions=["key_press", "click"],
        cache=cache,
    )
    frame = np.zeros((2, 2, 3), dtype=np.uint8)
    action = agent.decide(frame, state_sig="hello|world")
    assert action.action == "key_press"
    assert action.params == {"key": "space"}
    assert call_count == 0


def test_vlm_agent_cache_miss_calls_backend(tmp_path: Path) -> None:
    """Cache miss triggers backend call and caches the result."""
    call_count = 0

    class CountingBackend:
        def complete(self, prompt: str, image: np.ndarray) -> str:
            nonlocal call_count
            call_count += 1
            return json.dumps({"action": "click", "params": {"button": "left"}})

    cache = SkillCache.__new__(SkillCache)
    cache._data = {}
    cache._path = tmp_path / "skills.json"
    cache._outcomes = {}
    cache.put = lambda sig, action: cache._data.__setitem__(sig, action)  # type: ignore[assignment]

    agent = VLMAgent(
        backend=CountingBackend(),
        allowed_actions=["click"],
        cache=cache,
    )
    frame = np.zeros((2, 2, 3), dtype=np.uint8)
    action = agent.decide(frame, state_sig="new|sig")
    assert action.action == "click"
    assert call_count == 1
    # Verify cached
    assert cache.get("new|sig") is not None


def test_vlm_agent_does_not_reuse_unverified_cached_action(tmp_path: Path) -> None:
    class CountingBackend:
        def __init__(self) -> None:
            self.calls = 0

        def complete(self, prompt: str, image: np.ndarray) -> str:
            self.calls += 1
            return json.dumps({"action": "click", "params": {"button": "left"}})

    cache = SkillCache.__new__(SkillCache)
    cache._data = {}
    cache._path = tmp_path / "skills.json"
    cache._outcomes = {}
    cache.put("screen", {"action": "key_press", "params": {"key": "space"}})
    backend = CountingBackend()
    agent = VLMAgent(backend=backend, allowed_actions=["key_press", "click"], cache=cache)
    action = agent.decide(np.zeros((8, 8, 3), dtype="uint8"), state_sig="screen")
    assert action.action == "click"
    assert backend.calls == 1


def test_record_outcome_tracks_counts(tmp_path: Path) -> None:
    cache = SkillCache(path=tmp_path / "skills.json")
    cache.put("sig1", {"action": "click", "params": {}})
    cache.record_outcome("sig1", success=True)
    cache.record_outcome("sig1", success=False)
    cache.record_outcome("sig1", success=True)
    assert cache._outcomes["sig1"] == {"good": 2, "bad": 1}


def test_prune_after_two_fails_of_three(tmp_path: Path) -> None:
    cache = SkillCache(path=tmp_path / "skills.json")
    cache.put("bad_sig", {"action": "noop", "params": {}})
    cache.record_outcome("bad_sig", success=False)
    cache.record_outcome("bad_sig", success=False)
    cache.record_outcome("bad_sig", success=False)
    # Third fail should trigger pruning (bad=3 >= 2/3 of total=3)
    result = cache.get("bad_sig")
    assert result is None
    assert cache.get("bad_sig") is None


def test_successful_skills_survive(tmp_path: Path) -> None:
    cache = SkillCache(path=tmp_path / "skills.json")
    cache.put("good_sig", {"action": "key_press", "params": {"key": "w"}})
    cache.record_outcome("good_sig", success=True)
    cache.record_outcome("good_sig", success=True)
    cache.record_outcome("good_sig", success=True)
    result = cache.get("good_sig")
    assert result is not None
    assert result["action"] == "key_press"


def test_prune_not_triggered_below_min_outcomes(tmp_path: Path) -> None:
    cache = SkillCache(path=tmp_path / "skills.json")
    cache.put("early_sig", {"action": "click", "params": {}})
    cache.record_outcome("early_sig", success=False)
    cache.record_outcome("early_sig", success=False)
    # Only 2 outcomes (< 3), should not prune
    result = cache.get("early_sig")
    assert result is not None


def test_prune_not_triggered_at_boundary(tmp_path: Path) -> None:
    cache = SkillCache(path=tmp_path / "skills.json")
    cache.put("boundary_sig", {"action": "click", "params": {}})
    cache.record_outcome("boundary_sig", success=False)
    cache.record_outcome("boundary_sig", success=False)
    cache.record_outcome("boundary_sig", success=True)
    # 3 outcomes, bad=2 (2/3 >= 2/3), should prune
    result = cache.get("boundary_sig")
    assert result is None


def test_put_invalidates_verified_outcomes_when_action_changes(tmp_path: Path) -> None:
    """An oracle result for an old action cannot certify a replacement action."""
    cache = SkillCache(path=tmp_path / "skills.json")
    cache.put("sig_x", {"action": "click", "params": {}})
    cache.record_outcome("sig_x", success=True)
    cache.record_outcome("sig_x", success=False)
    cache.record_outcome("sig_x", success=True)
    # Overwrite with a new action — old counts no longer apply.
    cache.put("sig_x", {"action": "key_press", "params": {"key": "w"}})
    assert "sig_x" not in cache._outcomes
    # Verify invalidation persists after reload.
    cache2 = SkillCache(path=tmp_path / "skills.json")
    assert "sig_x" not in cache2._outcomes


def test_record_outcome_persists(tmp_path: Path) -> None:
    """record_outcome() should persist stats to disk."""
    path = tmp_path / "skills.json"
    cache = SkillCache(path=path)
    cache.put("p", {"action": "noop", "params": {}})
    cache.record_outcome("p", success=True)
    cache.record_outcome("p", success=False)
    cache2 = SkillCache(path=path)
    assert cache2._outcomes["p"] == {"good": 1, "bad": 1}


def test_legacy_frame_reward_stats_are_not_trusted(tmp_path: Path) -> None:
    path = tmp_path / "legacy.json"
    path.write_text(json.dumps({
        "actions": {"screen": {"action": "key_press", "params": {"key": "w"}}},
        "stats": {"screen": {"good": 10, "bad": 0}},
    }), encoding="utf-8")
    cache = SkillCache(path=path)
    assert cache.get("screen") is not None
    assert cache.get_verified("screen") is None
    assert cache._outcomes == {}


def test_failed_oracle_outcome_does_not_enable_cache_reuse(tmp_path: Path) -> None:
    cache = SkillCache(path=tmp_path / "skills.json")
    cache.put("screen", {"action": "key_press", "params": {"key": "space"}})
    cache.record_outcome("screen", success=False)
    assert cache.get_verified("screen") is None


def test_best_sig_prefix_picks_highest_ratio(tmp_path: Path) -> None:
    """best_sig_prefix returns the entry with the best success ratio."""
    cache = SkillCache(path=tmp_path / "skills.json")
    cache.put("ocr1|aaaabbbbccccddddeeeeffff00112233", {"action": "a1", "params": {}})
    cache.record_outcome("ocr1|aaaabbbbccccddddeeeeffff00112233", success=False)
    cache.record_outcome("ocr1|aaaabbbbccccddddeeeeffff00112233", success=False)

    cache.put("ocr1|bbbbccccddddeeeeffff00112233aaaa", {"action": "a2", "params": {}})
    cache.record_outcome("ocr1|bbbbccccddddeeeeffff00112233aaaa", success=True)
    cache.record_outcome("ocr1|bbbbccccddddeeeeffff00112233aaaa", success=True)

    best = cache.best_sig_prefix("ocr1")
    assert best is not None
    assert best["action"] == "a2"


def test_best_sig_prefix_requires_one_sample(tmp_path: Path) -> None:
    """best_sig_prefix skips entries with zero recorded outcomes."""
    cache = SkillCache(path=tmp_path / "skills.json")
    cache.put("ocr2|aaaa", {"action": "no_samples", "params": {}})
    # No outcomes recorded for this entry
    best = cache.best_sig_prefix("ocr2")
    assert best is None


def test_best_sig_prefix_no_match(tmp_path: Path) -> None:
    """best_sig_prefix returns None when no sigs match the prefix."""
    cache = SkillCache(path=tmp_path / "skills.json")
    cache.put("other|aaaa", {"action": "x", "params": {}})
    cache.record_outcome("other|aaaa", success=True)
    best = cache.best_sig_prefix("nonexistent")
    assert best is None


def test_extract_ocr_prefix_strips_visual_hash() -> None:
    sig = "apple|banana|aaaabbbbccccddddeeeeffff00112233"
    assert SkillCache.extract_ocr_prefix(sig) == "apple|banana"


def test_extract_ocr_prefix_no_visual_hash() -> None:
    sig = "apple|banana"
    assert SkillCache.extract_ocr_prefix(sig) == "apple|banana"


def test_extract_ocr_prefix_single_word() -> None:
    sig = "hello|1234567890abcdef1234567890abcdef"
    assert SkillCache.extract_ocr_prefix(sig) == "hello"


def test_vlm_agent_fuzzy_cache_hit(tmp_path: Path) -> None:
    """VLMAgent uses fuzzy prefix match when exact sig misses."""
    call_count = 0

    class CountingBackend:
        def complete(self, prompt: str, image: np.ndarray) -> str:
            nonlocal call_count
            call_count += 1
            return json.dumps({"action": "click", "params": {"button": "left"}})

    cache = SkillCache.__new__(SkillCache)
    cache._data = {}
    cache._path = tmp_path / "skills.json"
    cache._outcomes = {}
    # Put entry with OCR prefix "ocr1" and a specific visual hash
    sig_existing = "ocr1|aaaabbbbccccddddeeeeffff00112233"
    cache.put(sig_existing, {"action": "key_press", "params": {"key": "w"}})
    cache.record_outcome(sig_existing, success=True)

    agent = VLMAgent(
        backend=CountingBackend(),
        allowed_actions=["key_press", "click"],
        cache=cache,
    )
    frame = np.zeros((2, 2, 3), dtype=np.uint8)
    # Different visual hash, same OCR prefix → fuzzy hit
    sig_query = "ocr1|bbbbccccddddeeeeffff00112233aaaa"
    action = agent.decide(frame, state_sig=sig_query)
    assert action.action == "key_press"
    assert action.params == {"key": "w"}
    assert call_count == 0  # no VLM call


def test_rank_by_ocr_orders_by_ratio(tmp_path: Path) -> None:
    """rank_by_ocr returns entries with matching OCR part sorted by ratio desc."""
    cache = SkillCache(path=tmp_path / "skills.json")
    # Two entries share the same OCR part "menu", different visual hashes.
    sig_low = "menu|aaaabbbbccccddddeeeeffff00112233"
    sig_high = "menu|bbbbccccddddeeeeffff00112233aaaa"
    cache.put(sig_low, {"action": "a_low", "params": {}})
    cache.record_outcome(sig_low, success=True)
    cache.record_outcome(sig_low, success=True)
    cache.record_outcome(sig_low, success=False)  # ratio = 2/3
    cache.put(sig_high, {"action": "a_high", "params": {}})
    cache.record_outcome(sig_high, success=True)
    cache.record_outcome(sig_high, success=True)  # ratio = 1.0

    ranked = cache.rank_by_ocr("menu")
    assert len(ranked) == 2
    assert ranked[0]["sig"] == sig_high
    assert ranked[0]["ratio"] == 1.0
    assert ranked[1]["sig"] == sig_low
    assert ranked[1]["params"] == {}


def test_rank_by_ocr_filters_low_ratio(tmp_path: Path) -> None:
    """Entries with success ratio < 0.5 are excluded."""
    cache = SkillCache(path=tmp_path / "skills.json")
    sig = "lobby|aaaabbbbccccddddeeeeffff00112233"
    cache.put(sig, {"action": "a", "params": {}})
    cache.record_outcome(sig, success=False)
    cache.record_outcome(sig, success=False)
    cache.record_outcome(sig, success=True)  # ratio = 1/3 < 0.5

    ranked = cache.rank_by_ocr("lobby")
    assert ranked == []


def test_rank_by_ocr_filters_no_samples(tmp_path: Path) -> None:
    """Entries with zero recorded outcomes are excluded."""
    cache = SkillCache(path=tmp_path / "skills.json")
    sig = "start|aaaabbbbccccddddeeeeffff00112233"
    cache.put(sig, {"action": "a", "params": {}})
    # no record_outcome call

    ranked = cache.rank_by_ocr("start")
    assert ranked == []


def test_rank_by_ocr_empty_when_no_match(tmp_path: Path) -> None:
    """Returns empty list when no entry shares the OCR part."""
    cache = SkillCache(path=tmp_path / "skills.json")
    cache.put("other|aaaabbbbccccddddeeeeffff00112233", {"action": "a", "params": {}})
    cache.record_outcome("other|aaaabbbbccccddddeeeeffff00112233", success=True)

    ranked = cache.rank_by_ocr("nonexistent")
    assert ranked == []


def test_rank_by_ocr_top_k_limit(tmp_path: Path) -> None:
    """rank_by_ocr truncates results to top_k entries."""
    cache = SkillCache(path=tmp_path / "skills.json")
    for i in range(5):
        sig = f"multi|{i:032x}"
        cache.put(sig, {"action": f"a{i}", "params": {}})
        cache.record_outcome(sig, success=True)

    ranked = cache.rank_by_ocr("multi", top_k=2)
    assert len(ranked) == 2
    assert all(r["ratio"] == 1.0 for r in ranked)
