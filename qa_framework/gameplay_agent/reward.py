from __future__ import annotations

import numpy as np

from .skill_cache import _visual_hash


class FrameDiffReward:
    """Pseudo-reward based on visual hash difference between consecutive frames.

    Returns 0.0 on the first frame, 1.0 if the screen changed, 0.0 if unchanged.
    """

    def __init__(self) -> None:
        self._prev_hash: str | None = None
        self.changed: bool = False

    def update(self, frame: np.ndarray) -> float:
        """Compute reward by comparing *frame* against the previous frame.

        Sets ``self.changed`` to True when the visual hash differs.
        """
        h = _visual_hash(frame)
        if self._prev_hash is None:
            self.changed = False
        else:
            self.changed = h != self._prev_hash
        self._prev_hash = h
        return 1.0 if self.changed else 0.0
