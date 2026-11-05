"""Tests for AdversarialVisionGuard."""
from __future__ import annotations

import numpy as np

from qa_framework.adversarial_vision import AdversarialVisionGuard


class TestAdversarialVisionGuard:
    def setup_method(self):
        self.guard = AdversarialVisionGuard()

    def test_clean_frame_passes(self):
        frame = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)
        result = self.guard.validate(frame)
        assert result.score > 0.7

    def test_flat_frame_flagged(self):
        frame = np.zeros((480, 640, 3), dtype=np.uint8)  # All black
        result = self.guard.validate(frame)
        assert result.score < 0.5

    def test_low_variance_flagged(self):
        frame = np.full((480, 640, 3), 128, dtype=np.uint8)  # Uniform gray
        result = self.guard.validate(frame)
        assert result.score < 0.7

    def test_stutter_detection(self):
        frame = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)
        # Submit same frame 5 times
        for _ in range(5):
            result = self.guard.validate(frame)
        assert result.score < 1.0
        assert any("stutter" in w for w in result.warnings)

    def test_trust_score_fields(self):
        frame = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)
        result = self.guard.validate(frame)
        assert isinstance(result.histogram_spread, float)
        assert isinstance(result.frame_variance, float)
        assert isinstance(result.warnings, list)
