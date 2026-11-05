"""Memory curation primitives for UGAFStudio QA — state graph, consolidation, skill tracking.

Per 2026 agent memory consolidation patterns (Anthropic Dreaming analog):
- KnownStateGraph: O(1) state recognition with similarity matching
- MemoryCurator: async consolidation pass (StateCache → KnownStateGraph)
- SkillTracker: usage-based pruning to prevent skill accumulation
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any

# ---------------------------------------------------------------------------
# KnownStateGraph — graph of known game states for O(1) recognition
# ---------------------------------------------------------------------------

class KnownStateGraph:
    """Graph of known game states for O(1) recognition.

    Maps visual-hash + OCR signatures to verified outcomes.
    Supports similarity matching for near-duplicate states.

    Example::

        graph = KnownStateGraph()
        graph.add_state("hash_abc_ocr_menu", {"result": "pass", "cost_saved": 0.05})
        state = graph.lookup("hash_abc_ocr_menu")  # exact hit
        similar = graph.lookup_similar("hash_abc_ocr_menu", threshold=0.8)  # fuzzy match
    """

    def __init__(self, similarity_threshold: float = 0.85) -> None:
        self.similarity_threshold = similarity_threshold
        self._states: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()

    def add_state(self, state_key: str, outcome: dict[str, Any]) -> None:
        """Register a known state with its outcome."""
        with self._lock:
            self._states[state_key] = {
                "outcome": outcome,
                "added_at": time.monotonic(),
                "access_count": 0,
            }

    def lookup(self, state_key: str) -> dict[str, Any] | None:
        """Exact match lookup."""
        with self._lock:
            entry = self._states.get(state_key)
            if entry is not None:
                entry["access_count"] += 1
                return entry["outcome"]
            return None

    def lookup_similar(self, state_key: str, threshold: float | None = None) -> dict[str, Any] | None:
        """Find a similar state using Jaccard similarity on key tokens."""
        threshold = threshold if threshold is not None else self.similarity_threshold
        with self._lock:
            best_match: dict[str, Any] | None = None
            best_score: float = 0.0

            query_tokens = set(state_key.split("_"))

            for known_key, entry in self._states.items():
                known_tokens = set(known_key.split("_"))
                if not query_tokens or not known_tokens:
                    continue
                intersection = query_tokens & known_tokens
                union = query_tokens | known_tokens
                score = len(intersection) / len(union) if union else 0.0

                if score > best_score and score >= threshold:
                    best_score = score
                    best_match = entry["outcome"]

            return best_match

    def stats(self) -> dict[str, Any]:
        """Return graph statistics."""
        with self._lock:
            return {
                "total_states": len(self._states),
                "total_accesses": sum(e["access_count"] for e in self._states.values()),
            }


# ---------------------------------------------------------------------------
# MemoryCurator — async memory consolidation (Dreaming analog)
# ---------------------------------------------------------------------------

@dataclass
class MemoryCurator:
    """Async memory consolidation — Dreaming analog for QA framework.

    Reviews StateCache, evicts stale entries, consolidates recurring
    state signatures into KnownStateGraph for O(1) recognition.
    """
    state_cache: Any
    known_graph: KnownStateGraph = field(default_factory=KnownStateGraph)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def consolidate(self) -> dict[str, Any]:
        """Run consolidation pass. Returns stats."""
        with self._lock:
            stats: dict[str, Any] = {
                "states_reviewed": 0,
                "states_consolidated": 0,
                "stale_evicted": 0,
                "timestamp": time.monotonic(),
            }

            store = getattr(self.state_cache, "_store", {})
            keys_to_evict: list[str] = []
            keys_to_consolidate: list[tuple[str, dict[str, Any]]] = []

            for key, entry in list(store.items()):
                stats["states_reviewed"] += 1

                if time.monotonic() > entry.expires_at:
                    keys_to_evict.append(key)
                    stats["stale_evicted"] += 1
                    continue

                value = entry.value
                if isinstance(value, dict) and value.get("result") == "pass":
                    keys_to_consolidate.append((key, value))

            for key in keys_to_evict:
                self.state_cache.invalidate(key)

            for key, value in keys_to_consolidate:
                self.known_graph.add_state(key, value)
                stats["states_consolidated"] += 1

            return stats

    def get_graph_stats(self) -> dict[str, Any]:
        """Return KnownStateGraph statistics."""
        return self.known_graph.stats()


# ---------------------------------------------------------------------------
# SkillTracker — usage-based pruning
# ---------------------------------------------------------------------------

@dataclass
class SkillUsageEntry:
    """Track usage metrics for a single skill."""
    count: int = 0
    last_used: float = 0.0
    first_used: float = 0.0


class SkillTracker:
    """Track skill usage for pruning decisions.

    Records how often and how recently each skill is used.
    Skills unused for > max_age_seconds are prune candidates.

    Example::

        tracker = SkillTracker(max_age_seconds=86400 * 30)
        tracker.record_use("playbook-system")
        tracker.record_use("playbook-system")
        tracker.get_use_count("playbook-system")  # 2
        tracker.get_prune_candidates()  # skills unused for > 30 days
    """

    def __init__(self, max_age_seconds: float = 86400.0 * 30) -> None:
        self.max_age_seconds = max_age_seconds
        self._usage: dict[str, SkillUsageEntry] = {}
        self._lock = threading.RLock()

    def record_use(self, skill_name: str) -> None:
        """Record a skill usage event."""
        with self._lock:
            now = time.monotonic()
            entry = self._usage.get(skill_name)
            if entry is None:
                self._usage[skill_name] = SkillUsageEntry(
                    count=1, last_used=now, first_used=now
                )
            else:
                entry.count += 1
                entry.last_used = now

    def get_use_count(self, skill_name: str) -> int:
        """Return the number of times a skill has been used."""
        with self._lock:
            entry = self._usage.get(skill_name)
            return entry.count if entry else 0

    def get_prune_candidates(self) -> list[str]:
        """Return skills unused for longer than max_age_seconds."""
        with self._lock:
            now = time.monotonic()
            return [
                name for name, entry in self._usage.items()
                if now - entry.last_used > self.max_age_seconds
            ]

    def stats(self) -> dict[str, Any]:
        """Return SkillTracker statistics."""
        with self._lock:
            return {
                "total_skills": len(self._usage),
                "total_uses": sum(e.count for e in self._usage.values()),
                "prune_candidates": len(self.get_prune_candidates()),
            }
