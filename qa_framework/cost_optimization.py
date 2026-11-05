"""Cost optimization primitives for UGAFStudio QA — token budgets, state caching, routing.

Per 2026 production agent cost reduction patterns:
- TokenBudget: per-step token budget enforcement with thread-safe tracking
- StateCache: cache for visual/OCR state to avoid redundant VLM calls (TTL-based)
- CostAwareRouter: route verification tasks by cost tier (cheap/medium/expensive)
- ContextBuilder: build LLM context respecting token budget with automatic truncation
- EvaluationSubset: select deterministic subset of checkpoints for efficient recurring evaluation
"""
from __future__ import annotations

import random
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

# ---------------------------------------------------------------------------
# TokenBudget — per-step token budget enforcement
# ---------------------------------------------------------------------------

@dataclass
class TokenBudget:
    """Enforce per-step token budget with thread-safe tracking.

    Example::

        budget = TokenBudget(max_tokens=1000)
        if budget.can_spend(500):
            budget.spend(500)
        # budget.remaining == 500
    """
    max_tokens: int
    _spent: int = 0
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def can_spend(self, tokens: int) -> bool:
        with self._lock:
            return self._spent + tokens <= self.max_tokens

    def spend(self, tokens: int) -> bool:
        """Attempt to spend tokens. Returns False if would exceed budget."""
        with self._lock:
            if self._spent + tokens > self.max_tokens:
                return False
            self._spent += tokens
            return True

    @property
    def remaining(self) -> int:
        with self._lock:
            return self.max_tokens - self._spent

    @property
    def spent(self) -> int:
        with self._lock:
            return self._spent

    def reset(self) -> None:
        with self._lock:
            self._spent = 0

    def to_dict(self) -> dict[str, Any]:
        with self._lock:
            return {
                "max_tokens": self.max_tokens,
                "spent": self._spent,
                "remaining": self.max_tokens - self._spent,
                "utilization": round(self._spent / self.max_tokens, 4) if self.max_tokens > 0 else 0.0,
            }


# ---------------------------------------------------------------------------
# StateCache — cache for visual/OCR state to avoid redundant VLM calls
# ---------------------------------------------------------------------------

@dataclass
class CacheEntry:
    value: object
    expires_at: float


class StateCache:
    """Cache for visual/OCR state to avoid redundant VLM calls.

    Key = visual hash + OCR words concatenated. Value = verification result.
    TTL-based expiration prevents stale state from persisting.

    Example::

        cache = StateCache(ttl_seconds=300)
        key = "hash_abc_ocr_menu_play"
        cache.set(key, {"result": "pass", "cost_saved": 0.05})
        result = cache.get(key)  # hit -> {"result": "pass", "cost_saved": 0.05}
    """

    def __init__(self, ttl_seconds: float = 300.0, max_size: int = 1000) -> None:
        self.ttl_seconds = ttl_seconds
        self.max_size = max_size
        self._store: dict[str, CacheEntry] = {}
        self._lock = threading.Lock()
        self.hit_count = 0
        self.miss_count = 0

    def get(self, key: str) -> object | None:
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                self.miss_count += 1
                return None
            if time.monotonic() > entry.expires_at:
                del self._store[key]
                self.miss_count += 1
                return None
            self.hit_count += 1
            return entry.value

    def set(self, key: str, value: object) -> None:
        with self._lock:
            if len(self._store) >= self.max_size:
                # Evict oldest by expiration
                oldest_key = min(self._store, key=lambda k: self._store[k].expires_at)
                del self._store[oldest_key]
            self._store[key] = CacheEntry(value=value, expires_at=time.monotonic() + self.ttl_seconds)

    def invalidate(self, key: str) -> None:
        with self._lock:
            self._store.pop(key, None)

    def clear(self) -> None:
        with self._lock:
            self._store.clear()
            self.hit_count = 0
            self.miss_count = 0

    @property
    def size(self) -> int:
        with self._lock:
            return len(self._store)

    def to_dict(self) -> dict[str, Any]:
        with self._lock:
            return {
                "size": len(self._store),
                "max_size": self.max_size,
                "hit_count": self.hit_count,
                "miss_count": self.miss_count,
                "hit_rate": round(self.hit_count / max(1, self.hit_count + self.miss_count), 4),
            }


# ---------------------------------------------------------------------------
# CostAwareRouter — route verification tasks by cost tier
# ---------------------------------------------------------------------------

class CostTier(str, Enum):
    """Cost tier for verification tasks."""
    CHEAP = "cheap"          # deterministic code path, no LLM
    MEDIUM = "medium"        # cached or lightweight LLM
    EXPENSIVE = "expensive"  # full VLM reasoning


class CostAwareRouter:
    """Route verification tasks by cost tier to minimize token usage.

    Based on 2026 pattern: cheap models for classification/routing,
    expensive models for reasoning. Hybrid approach cuts costs ~72%.

    Example::

        router = CostAwareRouter()
        tier = router.route("frame_diff")  # "cheap"
        tier = router.route("anomaly_root_cause")  # "expensive"
    """

    CHEAP_TASKS: frozenset[str] = frozenset({
        "frame_diff", "process_alive", "file_exists",
        "window_rendered", "checkpoint_complete", "idempotency_check",
        "cost_check", "token_budget_check", "state_cache_lookup",
        "layout_bounds_check", "pixel_color_check",
    })

    MEDIUM_TASKS: frozenset[str] = frozenset({
        "state_ocr", "visual_hash_match", "color_detect",
        "layout_verify", "state_cache_lookup", "text_ocr",
        "element_detect",
    })

    EXPENSIVE_TASKS: frozenset[str] = frozenset({
        "anomaly_root_cause", "gameplay_analysis", "narrative_understanding",
        "bug_classification", "regression_diagnosis", "vlm_verify",
        "llm_anomaly_analysis", "gameplay_qa",
    })

    COST_USD_PER_TIER: dict[str, float] = {
        CostTier.CHEAP: 0.0,
        CostTier.MEDIUM: 0.001,
        CostTier.EXPENSIVE: 0.05,
    }

    def route(self, task_name: str) -> str:
        """Return cost tier for a given task name."""
        if task_name in self.CHEAP_TASKS:
            return CostTier.CHEAP
        if task_name in self.EXPENSIVE_TASKS:
            return CostTier.EXPENSIVE
        return CostTier.MEDIUM

    def estimated_cost_usd(self, task_name: str) -> float:
        """Return estimated USD cost for a given task."""
        tier = self.route(task_name)
        return self.COST_USD_PER_TIER[tier]

    def is_cheap(self, task_name: str) -> bool:
        return self.route(task_name) == CostTier.CHEAP

    def is_expensive(self, task_name: str) -> bool:
        return self.route(task_name) == CostTier.EXPENSIVE


# ---------------------------------------------------------------------------
# ContextBuilder — build LLM context respecting token budget
# ---------------------------------------------------------------------------

@dataclass
class _Section:
    name: str
    content: str
    priority: int


class ContextBuilder:
    """Build LLM context respecting token budget with automatic truncation.

    Sections are added with a priority (lower = kept first when truncating).
    When context exceeds max_tokens, lowest-priority sections are truncated or dropped.

    Example::

        builder = ContextBuilder(max_tokens=1000)
        builder.add_section("system", "You are a QA bot.", priority=1)
        builder.add_section("frame_data", large_base64_string, priority=5)
        context = builder.build()  # fits within budget
    """

    def __init__(self, max_tokens: int) -> None:
        self.max_tokens = max_tokens
        self._sections: list[_Section] = []
        self._lock = threading.Lock()

    def add_section(self, name: str, content: str, priority: int = 5) -> None:
        """Add a section. Lower priority number = kept first when truncating."""
        with self._lock:
            self._sections.append(_Section(name=name, content=content, priority=priority))
            self._sections.sort(key=lambda s: s.priority)

    def build(self) -> str:
        """Build context string, truncating lowest-priority sections to fit budget."""
        with self._lock:
            # Conservative token estimate: 1 token ≈ 2 chars (mixed content)
            def estimate_tokens(text: str) -> int:
                return max(1, len(text) // 2)

            result: list[str] = []
            remaining = self.max_tokens

            for section in self._sections:
                needed = estimate_tokens(section.content)
                if needed <= remaining:
                    result.append(f"[{section.name}]\n{section.content}\n")
                    remaining -= needed
                else:
                    # Truncate to fit remaining budget
                    available_chars = remaining * 2
                    if available_chars > 10:  # only include if meaningful space left
                        truncated = section.content[:available_chars] + "...[TRUNCATED]"
                        result.append(f"[{section.name}]\n{truncated}\n")
                    remaining = 0
                    break

            return "\n".join(result)

    def clear(self) -> None:
        with self._lock:
            self._sections.clear()

    @property
    def section_count(self) -> int:
        with self._lock:
            return len(self._sections)


# ---------------------------------------------------------------------------
# EvaluationSubset — select deterministic subset for efficient recurring evaluation
# ---------------------------------------------------------------------------

class EvaluationSubset:
    """Select a deterministic subset of checkpoints for recurring evaluation.

    Based on arXiv 2609.21267: efficient recurring evaluation for production agents.
    Instead of full benchmark rerun, sample a subset to detect regression early.

    Example::

        checkpoints = ["file_check", "frame_diff", "ocr_verify", "anomaly_detect"]
        subset = EvaluationSubset(checkpoints, sample_ratio=0.4, seed=42)
        selected = subset.select()  # 2 checkpoints, deterministic
    """

    def __init__(self, checkpoints: list[str], sample_ratio: float = 0.3, seed: int = 42) -> None:
        self.checkpoints = list(checkpoints)
        self.sample_ratio = max(0.0, min(1.0, sample_ratio))
        self.seed = seed

    def select(self) -> list[str]:
        """Select a deterministic subset of checkpoints."""
        rng = random.Random(self.seed)
        k = max(1, int(len(self.checkpoints) * self.sample_ratio))
        return rng.sample(self.checkpoints, k)

    def select_by_cost_tier(self, router: CostAwareRouter) -> dict[str, list[str]]:
        """Select subset stratified by cost tier for balanced evaluation.

        Returns dict of tier -> checkpoint list, ensuring each tier
        is represented in the evaluation subset.
        """
        by_tier: dict[str, list[str]] = {"cheap": [], "medium": [], "expensive": []}
        for cp in self.checkpoints:
            tier = router.route(cp)
            by_tier[tier].append(cp)

        result: dict[str, list[str]] = {}
        for tier, cps in by_tier.items():
            if not cps:
                continue
            rng = random.Random(self.seed + hash(tier) % 1000)
            k = max(1, int(len(cps) * self.sample_ratio))
            result[tier] = rng.sample(cps, k)
        return result

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_checkpoints": len(self.checkpoints),
            "sample_ratio": self.sample_ratio,
            "seed": self.seed,
            "selected_count": len(self.select()),
        }
