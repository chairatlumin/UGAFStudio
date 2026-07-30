from __future__ import annotations

import mss
import numpy as np


class CaptureService:
    """Desktop screen capture service."""

    def __init__(self) -> None:
        self._mss = mss.mss()
        self._monitor = self._mss.monitors[1]

    def capture(self) -> np.ndarray:
        """
        Capture the selected monitor.

        Returns:
            numpy.ndarray: BGRA image.
        """
        screenshot = self._mss.grab(self._monitor)

        return np.asarray(screenshot)

    def set_monitor(self, monitor_index: int) -> None:
        """
        Change capture monitor.

        Monitor 1 = Primary Monitor
        """

        if 0 < monitor_index < len(self._mss.monitors):
            self._monitor = self._mss.monitors[monitor_index]

    def monitor_size(self) -> tuple[int, int]:
        """Return monitor width and height."""

        return (
            self._monitor["width"],
            self._monitor["height"],
        )
