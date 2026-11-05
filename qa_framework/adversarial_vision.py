from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class VisionTrustScore:
    score: float  # 0.0 adversarial → 1.0 clean
    warnings: list[str]
    histogram_spread: float
    frame_variance: float


class AdversarialVisionGuard:
    """Vision input validation to detect adversarial/corrupted frames.

    Uses numpy for histogram and variance calculations.
    """

    def __init__(self, min_spread: float = 30.0, min_variance: float = 100.0) -> None:
        self.min_spread = min_spread
        self.min_variance = min_variance
        self._prev_hashes: list[str] = []
        self._stutter_count = 0

    # ── private helpers ────────────────────────────────────────────────

    def _histogram_spread(self, frame: np.ndarray) -> float:
        """Compute spread of non-zero histogram bins across channels.

        Returns the max difference between 90th and 10th percentile
        of non-zero counts per channel.
        """
        spreads: list[float] = []
        for ch in range(min(3, frame.shape[2])) if len(frame.shape) > 2 else [0]:
            ch_data = frame[:, :, ch] if len(frame.shape) > 2 else frame
            hist, _ = np.histogram(ch_data, bins=256, range=(0, 256))
            non_zero = hist[hist > 0]
            if len(non_zero) > 1:
                spreads.append(float(np.percentile(non_zero, 90) - np.percentile(non_zero, 10)))
            else:
                spreads.append(0.0)
        return float(max(spreads)) if spreads else 0.0

    def _frame_variance(self, frame: np.ndarray) -> float:
        """Compute variance of the frame."""
        return float(np.var(frame))

    def _frame_hash(self, frame: np.ndarray) -> str:
        """Create a small hash for frame comparison (stutter detection)."""
        # Use a minimal digest: flatten, quantize to 10 levels, then hash
        flat = frame.flatten()
        if flat.size > 0:
            quantized = (flat / 25.5).astype(np.int32)  # 0-10 range
            return str(hash(quantized.tobytes()))
        return "0"

    def _detect_stutter(self, frame: np.ndarray) -> None:
        """Detect 3+ identical consecutive frames."""
        h = self._frame_hash(frame)
        self._prev_hashes.append(h)
        if len(self._prev_hashes) > 5:
            self._prev_hashes.pop(0)

        # Count consecutive matches from the end
        count = 0
        for prev in reversed(self._prev_hashes[:-1]):
            if prev == self._prev_hashes[-1]:
                count += 1
            else:
                break
        self._stutter_count = count if count >= 3 else 0

    # ── public API ──────────────────────────────────────────────────────

    def validate(self, frame: np.ndarray) -> VisionTrustScore:
        """Validate a frame and return a trust score.

        A higher score means the frame is more likely to be clean/normal.
        A lower score (near 0.0) suggests the frame may be adversarial/
        corrupted.
        """
        # Compute histogram spread
        spread = self._histogram_spread(frame)

        # Compute frame variance
        variance = self._frame_variance(frame)

        # Detect stutter (3+ identical consecutive frames)
        self._detect_stutter(frame)
        is_stutter = self._stutter_count >= 3

        # Build score starting from 1.0 (clean)
        score = 1.0
        warnings: list[str] = []

        # Flat frame detection (low histogram spread)
        if spread < self.min_spread:
            score -= 0.3
            warnings.append(f"flat frame: spread={spread:.1f} < {self.min_spread}")

        # Low variance detection (uniform/blank frame)
        if variance < self.min_variance:
            score -= 0.3
            warnings.append(f"low variance: var={variance:.1f} < {self.min_variance}")

        # Stutter detection
        if is_stutter:
            score -= 0.2
            warnings.append(f"stutter detected: {self._stutter_count} identical frames")

        # Clamp to [0.0, 1.0]
        score = max(0.0, min(1.0, score))

        return VisionTrustScore(
            score=round(score, 2),
            warnings=warnings,
            histogram_spread=round(spread, 2),
            frame_variance=round(variance, 2),
        )
