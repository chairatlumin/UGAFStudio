from __future__ import annotations

from typing import TYPE_CHECKING

import mss
import numpy as np

from app.capture.monitor import MonitorInfo

if TYPE_CHECKING:
    from mss.base import MSSBase


class CaptureService:
    """Desktop screen capture service.

    The capture region defaults to the virtual desktop (all monitors as a
    single frame) so pixels on any monitor can be sampled. Individual monitors
    are addressable through :meth:`set_monitor`.
    """

    def __init__(self) -> None:
        self._mss: MSSBase = mss.MSS()
        self._monitors = self._read_monitors()
        self._monitor = self._monitors[0]

    def _read_monitors(self) -> list[MonitorInfo]:
        return [
            MonitorInfo(
                left=entry["left"],
                top=entry["top"],
                width=entry["width"],
                height=entry["height"],
            )
            for entry in self._mss.monitors
        ]

    def capture(self) -> np.ndarray:
        """
        Capture the current monitor region.

        Returns:
            numpy.ndarray: BGRA image.
        """
        return self.capture_region(self._monitor)

    def capture_region(self, monitor: MonitorInfo) -> np.ndarray:
        """
        Capture a screen region described by monitor bounds.

        Args:
            monitor: Region to capture, in screen coordinates.

        Returns:
            numpy.ndarray: BGRA image.
        """
        region = {
            "left": monitor.left,
            "top": monitor.top,
            "width": monitor.width,
            "height": monitor.height,
        }

        screenshot = self._mss.grab(region)

        return np.asarray(screenshot)

    def current_monitor(self) -> MonitorInfo:
        """Return the currently captured monitor region."""
        return self._monitor

    def all_monitors(self) -> list[MonitorInfo]:
        """Return all monitor regions; index 0 is the virtual desktop."""
        return list(self._monitors)

    def use_virtual_desktop(self) -> None:
        """Capture the virtual desktop spanning all monitors."""
        self._monitor = self._monitors[0]

    def set_monitor(self, monitor_index: int) -> None:
        """
        Change the capture region.

        Monitor 0 = Virtual Desktop, 1 = Primary Monitor, 2+ = additional.
        """
        if 0 <= monitor_index < len(self._monitors):
            self._monitor = self._monitors[monitor_index]

    def monitor_at(self, x: int, y: int) -> MonitorInfo:
        """Return the monitor containing a screen coordinate."""
        for monitor in self._monitors[1:]:
            if monitor.contains(x, y):
                return monitor

        return self._monitor

    def close(self) -> None:
        """Release the MSS operating-system capture resources."""
        self._mss.close()
