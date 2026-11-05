from __future__ import annotations

import enum
import threading
import time
from dataclasses import dataclass, field
from typing import Any


class CascadeLevel(enum.Enum):
    """Cost cascade levels (cheapest first)."""

    PERCEPTUAL_HASH = "perceptual_hash"  # ~0 cost
    OCR = "ocr"  # ~0.01 cost (Tesseract)
    VLM = "vlm"  # ~0.05-0.10 cost (API call)
    NONE = "none"  # no match


@dataclass
class CascadeStats:
    hits: int = 0
    misses: int = 0
    perceptual_hits: int = 0
    ocr_hits: int = 0
    vlm_calls: int = 0
    vlm_avoided: int = 0

    @property
    def total(self) -> int:
        return self.hits + self.misses


@dataclass
class CacheEntry:
    """A single cached state mapping."""

    key: str
    value: dict[str, Any]
    level: CascadeLevel
    created_at: float = field(default_factory=time.monotonic)
    access_count: int = 0


class CostCascadeRetriever:
    """Agentic RAG-style adaptive retrieval with cost cascade."""

    def __init__(self) -> None:
        self._perceptual: dict[str, CacheEntry] = {}
        self._ocr_index: dict[str, CacheEntry] = {}
        self._lock = threading.Lock()
        self.stats = CascadeStats()

    def seed(self, visual_hash: str, action: dict[str, Any]) -> None:
        """Seed perceptual-hash → action mapping."""
        with self._lock:
            self._perceptual[visual_hash] = CacheEntry(
                key=visual_hash,
                value=action,
                level=CascadeLevel.PERCEPTUAL_HASH,
            )

    def seed_ocr(self, ocr_signature: str, action: dict[str, Any]) -> None:
        """Seed OCR-signature → action mapping."""
        with self._lock:
            self._ocr_index[ocr_signature] = CacheEntry(
                key=ocr_signature,
                value=action,
                level=CascadeLevel.OCR,
            )

    def retrieve(
        self,
        visual_hash: str | None = None,
        ocr_words: list[str] | None = None,
    ) -> tuple[dict[str, Any] | None, CascadeLevel]:
        """Cascade: perceptual-hash → OCR → VLM fallback."""
        with self._lock:
            # Level 1: perceptual hash (instant, zero cost)
            if visual_hash and visual_hash in self._perceptual:
                entry = self._perceptual[visual_hash]
                entry.access_count += 1
                self.stats.hits += 1
                self.stats.perceptual_hits += 1
                self.stats.vlm_avoided += 1
                return entry.value, CascadeLevel.PERCEPTUAL_HASH

            # Level 2: OCR signature match (cheap)
            if ocr_words:
                sig = " ".join(sorted(w.upper() for w in ocr_words))
                for ocr_key, entry in self._ocr_index.items():
                    if ocr_key in sig or sig in ocr_key:
                        entry.access_count += 1
                        self.stats.hits += 1
                        self.stats.ocr_hits += 1
                        self.stats.vlm_avoided += 1
                        return entry.value, CascadeLevel.OCR

            # Level 3 would be VLM (expensive) — external call required
            self.stats.misses += 1
            return None, CascadeLevel.NONE
