from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class GamepadState:
    """Snapshot of gamepad buttons and axes."""

    buttons: dict[str, bool] = field(default_factory=dict)
    axes: dict[str, float] = field(default_factory=dict)


class GamepadService:
    """Reads gamepad state through the inputs library."""

    def __init__(self) -> None:
        self._inputs: Any = None

    def available(self) -> bool:
        """Return whether the gamepad backend can be loaded."""
        if self._inputs is None:
            try:
                import inputs

                self._inputs = inputs
            except ImportError, OSError:
                return False

        return True

    def poll(self, timeout: float = 0.1) -> GamepadState:
        """Return gamepad events accumulated since the previous poll."""
        buttons: dict[str, bool] = {}
        axes: dict[str, float] = {}

        if not self.available():
            return GamepadState(buttons=buttons, axes=axes)

        try:
            events = self._inputs.get_gamepad(timeout)
        except Exception:
            return GamepadState(buttons=buttons, axes=axes)

        for event in events:
            code = getattr(event, "code", "")
            state = getattr(event, "state", 0)

            if code.startswith("ABS_"):
                axes[code] = _normalize_axis(code, int(state))
            else:
                buttons[code] = bool(state)

        return GamepadState(buttons=buttons, axes=axes)


def _normalize_axis(code: str, state: int) -> float:
    if code in ("ABS_Z", "ABS_RZ"):
        return round(state / 255.0, 4)

    return round(state / 32767.0, 4)
