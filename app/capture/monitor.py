from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MonitorInfo:
    """Immutable bounds of a monitor or the virtual desktop."""

    left: int
    top: int
    width: int
    height: int

    @property
    def right(self) -> int:
        """Return exclusive right edge in screen coordinates."""
        return self.left + self.width

    @property
    def bottom(self) -> int:
        """Return exclusive bottom edge in screen coordinates."""
        return self.top + self.height

    @property
    def origin(self) -> tuple[int, int]:
        """Return top-left corner in screen coordinates."""
        return self.left, self.top

    @property
    def size(self) -> tuple[int, int]:
        """Return width and height."""
        return self.width, self.height

    def contains(self, x: int, y: int) -> bool:
        """Return whether a screen coordinate lies inside this monitor."""
        return self.left <= x < self.right and self.top <= y < self.bottom

    def to_local(self, x: int, y: int) -> tuple[int, int]:
        """Convert screen coordinates to monitor-local frame coordinates."""
        return x - self.left, y - self.top

    def to_global(self, x: int, y: int) -> tuple[int, int]:
        """Convert monitor-local frame coordinates to screen coordinates."""
        return x + self.left, y + self.top
