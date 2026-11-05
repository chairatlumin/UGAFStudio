from __future__ import annotations

import numpy as np

from qa_framework.gameplay_agent.reward import FrameDiffReward


def _make_frame(color: int = 100) -> np.ndarray:
    """Create a simple 8x8 BGR frame filled with a single color."""
    return np.full((8, 8, 3), color, dtype=np.uint8)


def test_first_update_returns_zero() -> None:
    r = FrameDiffReward()
    reward = r.update(_make_frame(100))
    assert reward == 0.0
    assert r.changed is False


def test_different_frames_return_one() -> None:
    r = FrameDiffReward()
    r.update(_make_frame(100))
    reward = r.update(_make_frame(200))
    assert reward == 1.0
    assert r.changed is True


def test_identical_frames_return_zero() -> None:
    r = FrameDiffReward()
    r.update(_make_frame(100))
    reward = r.update(_make_frame(100))
    assert reward == 0.0
    assert r.changed is False


def test_sequence_of_frames() -> None:
    r = FrameDiffReward()
    # first frame → 0
    assert r.update(_make_frame(10)) == 0.0
    # same → 0
    assert r.update(_make_frame(10)) == 0.0
    # different → 1
    assert r.update(_make_frame(99)) == 1.0
    # same again → 0
    assert r.update(_make_frame(99)) == 0.0
    # different → 1
    assert r.update(_make_frame(50)) == 1.0
