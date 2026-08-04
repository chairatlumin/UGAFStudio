from __future__ import annotations

import numpy as np

from app.utils.image import bgr_to_bgra


def test_bgr_to_bgra_adds_opaque_alpha() -> None:
    frame = np.zeros((2, 2, 3), dtype=np.uint8)
    frame[0, 0] = [10, 20, 30]

    result = bgr_to_bgra(frame)

    assert result.shape == (2, 2, 4)
    assert result.dtype == np.uint8
    assert result[0, 0].tolist() == [10, 20, 30, 255]
    assert (result[:, :, 3] == 255).all()


def test_bgr_to_bgra_rejects_wrong_channels() -> None:
    frame = np.zeros((2, 2, 4), dtype=np.uint8)

    try:
        bgr_to_bgra(frame)
    except ValueError:
        return

    raise AssertionError("Expected ValueError for non-BGR input")
