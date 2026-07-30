from __future__ import annotations

import time


class FPSCounter:
    """Calculate frames per second."""

    def __init__(self) -> None:
        self._last_time = time.perf_counter()
        self._fps = 0.0

    def tick(self) -> float:
        """Update FPS and return current value."""

        current = time.perf_counter()

        delta = current - self._last_time

        if delta > 0:
            self._fps = 1.0 / delta

        self._last_time = current

        return self._fps

    @property
    def fps(self) -> float:
        """Return latest FPS."""

        return self._fps
