from __future__ import annotations

import hashlib
import json
from collections import OrderedDict
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from loguru import logger

_MAX_ENTRIES = 200


def _visual_hash(frame: np.ndarray, prefix_len: int = 32) -> str:
    """Downscale frame to 16x16 grayscale, quantize to 2 bits, return hex prefix."""
    small = cv2.resize(frame, (16, 16), interpolation=cv2.INTER_AREA)
    if small.ndim == 3:
        gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
    else:
        gray = small
    quantized = (gray.astype(np.uint8) >> 6).astype(np.uint8)
    raw = quantized.tobytes()
    return hashlib.sha256(raw).hexdigest()[:prefix_len]


def signature(
    ocr_words: list[dict[str, Any]],
    frame: np.ndarray | None = None,
) -> str:
    """Derive a normalized state signature from OCR word list and optional frame.

    Keys on sorted lowercased word texts + visual hash prefix (first 32 hex
    chars of a 2-bit-quantized 16x16 grayscale hash).
    """
    words = sorted({w["text"].strip().lower() for w in ocr_words if w.get("text", "").strip()})
    ocr_part = "|".join(words)
    if frame is not None:
        try:
            vh = _visual_hash(frame)
            return f"{ocr_part}|{vh}"
        except Exception:
            logger.debug("visual hash failed, falling back to OCR-only signature")
    return ocr_part


class SkillCache:
    """LRU cache mapping state signatures to previously-successful actions.

    Persisted as JSON ``{sig: {"action": ..., "params": ...}}``.
    Max 200 entries with FIFO eviction.
    """

    _PRUNE_MIN_OUTCOMES = 3
    _PRUNE_FAIL_RATIO = 2 / 3

    def __init__(self, path: str | Path = "skills.json") -> None:
        self._path = Path(path)
        self._data: OrderedDict[str, dict[str, Any]] = OrderedDict()
        self._outcomes: dict[str, dict[str, int]] = {}
        if self._path.exists():
            self._load()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _ocr_part(sig: str) -> str:
        """Return the OCR-only part of *sig* (before the visual-hash segment).

        If *sig* contains no ``|``-separated visual hash, return *sig* unchanged.
        """
        parts = sig.split("|")
        # Signature format: "ocr_word1|ocr_word2|...|visual_hash"
        # OCR words are alphanumeric; visual hash is hex.  If the last segment
        # is all hex and length == 32, it's the visual hash — strip it.
        if len(parts) >= 2:
            last = parts[-1]
            if len(last) == 32 and all(c in "0123456789abcdef" for c in last):
                return "|".join(parts[:-1])
        return sig

    @staticmethod
    def extract_ocr_prefix(sig: str) -> str:
        """Public alias for :meth:`_ocr_part`."""
        return SkillCache._ocr_part(sig)

    def rank_by_ocr(self, ocr_words_sig_part: str, top_k: int = 3) -> list[dict[str, Any]]:
        """Return cached entries whose OCR part exactly matches *ocr_words_sig_part*.

        Each returned item is ``{"sig", "action", "params", "ratio"}`` and is
        filtered to have at least one recorded outcome and a success ratio
        ``good/(good+bad)`` of >= 0.5.  Results are sorted by ratio descending
        and truncated to *top_k*.
        """
        results: list[dict[str, Any]] = []
        for sig, entry in self._data.items():
            if self._ocr_part(sig) != ocr_words_sig_part:
                continue
            stats = self._outcomes.get(sig)
            if stats is None:
                continue
            total = stats["good"] + stats["bad"]
            if total < 1:
                continue
            ratio = stats["good"] / total
            if ratio < 0.5:
                continue
            results.append(
                {
                    "sig": sig,
                    "action": entry.get("action"),
                    "params": entry.get("params", {}),
                    "ratio": ratio,
                }
            )
        results.sort(key=lambda r: r["ratio"], reverse=True)
        return results[:top_k]

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _load(self) -> None:
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
            actions = raw.get("actions", {})
            # Older stats were learned from screen changes, not a profile's
            # explicit QA oracle. Keep their actions for inspection, but never
            # promote them into trusted cache outcomes.
            stats = raw.get("stats", {}) if raw.get("outcome_kind") == "verified_oracle" else {}
            for k, v in actions.items():
                self._data[k] = v
            for k, v in stats.items():
                self._outcomes[k] = {"good": v.get("good", 0), "bad": v.get("bad", 0)}
        except Exception as exc:
            logger.warning("SkillCache load failed: {}", exc)

    def save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": 2,
            "outcome_kind": "verified_oracle",
            "actions": dict(self._data),
            "stats": {k: dict(v) for k, v in self._outcomes.items()},
        }
        self._path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get(self, sig: str) -> dict[str, Any] | None:
        """Return cached action dict for *sig*, or ``None``.

        If the skill has ≥3 recorded outcomes and ≥2/3 were failures,
        the entry is pruned and ``None`` is returned.
        """
        stats = self._outcomes.get(sig)
        if stats is not None:
            total = stats["good"] + stats["bad"]
            if total >= self._PRUNE_MIN_OUTCOMES and stats["bad"] / total >= self._PRUNE_FAIL_RATIO:
                self._data.pop(sig, None)
                self.save()
                logger.info("pruned ineffective skill: {}", sig)
                return None
        return self._data.get(sig)

    def get_verified(self, sig: str) -> dict[str, Any] | None:
        """Return an action only after a profile-specific oracle recorded it."""
        stats = self._outcomes.get(sig)
        if stats is None or stats["good"] < 1:
            return None
        total = stats["good"] + stats["bad"]
        if total == 0 or stats["good"] / total < 0.5:
            return None
        return self.get(sig)

    def best_sig_prefix(self, prefix: str) -> dict[str, Any] | None:
        """Among entries whose sig starts with *prefix*, return the action entry
        with the highest success ratio ``good/(good+bad)`` (minimum 1 sample).

        Returns ``None`` if no matching entry has at least one recorded outcome.
        """
        best_entry: dict[str, Any] | None = None
        best_ratio = -1.0
        for sig, entry in self._data.items():
            if not sig.startswith(prefix):
                continue
            stats = self._outcomes.get(sig)
            if stats is None:
                continue
            total = stats["good"] + stats["bad"]
            if total < 1:
                continue
            ratio = stats["good"] / total
            if ratio > best_ratio:
                best_ratio = ratio
                best_entry = entry
        return best_entry

    def put(self, sig: str, action: dict[str, Any]) -> None:
        """Store an action dict under *sig* with FIFO eviction.

        Existing oracle counts are preserved only when the action is unchanged.
        """
        if sig in self._data:
            if self._data[sig] != action:
                self._outcomes.pop(sig, None)
            if hasattr(self._data, "move_to_end"):
                self._data.move_to_end(sig)
        else:
            # New entry – no prior counts
            pass
        self._data[sig] = action
        while len(self._data) > _MAX_ENTRIES:
            evicted_sig, _ = self._data.popitem(last=False)
            self._outcomes.pop(evicted_sig, None)
        self.save()

    def record_outcome(self, sig: str, success: bool) -> None:
        """Record an explicit oracle result for *sig* and persist it.

        Callers must not use frame difference or animation as a success oracle.
        """
        if sig not in self._outcomes:
            self._outcomes[sig] = {"good": 0, "bad": 0}
        if success:
            self._outcomes[sig]["good"] += 1
        else:
            self._outcomes[sig]["bad"] += 1
        self.save()
