from __future__ import annotations

import numpy as np


def bgr_to_bgra(frame: np.ndarray) -> np.ndarray:
    """Convert a BGR image to BGRA by adding an opaque alpha channel."""
    if frame.ndim != 3 or frame.shape[2] != 3:
        raise ValueError("Expected a BGR image with three channels")

    bgra = np.empty((frame.shape[0], frame.shape[1], 4), dtype=np.uint8)
    bgra[:, :, :3] = frame
    bgra[:, :, 3] = 255
    return bgra
