from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Callable

from app.input.keyboard_service import KeyboardService
from app.input.mouse_service import MouseService

ACTIONS = {"move", "click", "key", "write", "scroll"}


@dataclass(frozen=True)
class MacroStep:
    """A single recorded automation action."""

    action: str
    params: dict[str, Any] = field(default_factory=dict)
    delay_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MacroStep":
        return cls(
            action=str(data["action"]),
            params=dict(data.get("params", {})),
            delay_ms=float(data.get("delay_ms", 0.0)),
        )


class MacroRecorder:
    """Records mouse and keyboard actions with relative delays."""

    def __init__(self, clock: Callable[[], float] = time.perf_counter) -> None:
        self._clock = clock
        self._steps: list[MacroStep] = []
        self._last: float | None = None
        self._recording = False

    @property
    def recording(self) -> bool:
        return self._recording

    def start(self) -> None:
        """Begin a fresh recording."""
        self._steps.clear()
        self._last = None
        self._recording = True

    def stop(self) -> list[MacroStep]:
        """End recording and return the captured steps."""
        self._recording = False
        return list(self._steps)

    def record(self, action: str, params: dict[str, Any] | None = None) -> None:
        """Record an action tagged with the delay since the last one."""
        if not self._recording:
            return

        now = self._clock()
        delay = 0.0

        if self._last is not None:
            delay = (now - self._last) * 1000.0

        self._last = now

        self._steps.append(MacroStep(action=action, params=params or {}, delay_ms=round(delay, 3)))

    def record_move(self, x: int, y: int) -> None:
        self.record("move", {"x": x, "y": y})

    def record_click(self, x: int, y: int, button: str = "left") -> None:
        self.record("click", {"x": x, "y": y, "button": button})

    def record_key(self, key: str) -> None:
        self.record("key", {"key": key})

    def record_write(self, text: str) -> None:
        self.record("write", {"text": text})

    def record_scroll(self, amount: int) -> None:
        self.record("scroll", {"amount": amount})


class MacroPlayer:
    """Replays recorded macro steps through input services."""

    def __init__(
        self,
        mouse: MouseService,
        keyboard: KeyboardService,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._mouse = mouse
        self._keyboard = keyboard
        self._sleep = sleep

    def play(self, steps: list[MacroStep], speed: float = 1.0) -> None:
        """Replay steps at the given speed multiplier."""
        for step in steps:
            delay = step.delay_ms / 1000.0 / max(speed, 0.01)

            if delay > 0:
                self._sleep(delay)

            self._dispatch(step)

    def _dispatch(self, step: MacroStep) -> None:
        params = step.params

        if step.action == "move":
            self._mouse.move(int(params["x"]), int(params["y"]))
        elif step.action == "click":
            self._mouse.click(
                params.get("x"),
                params.get("y"),
                button=str(params.get("button", "left")),
            )
        elif step.action == "key":
            self._keyboard.press(str(params["key"]))
        elif step.action == "write":
            self._keyboard.write(str(params["text"]))
        elif step.action == "scroll":
            self._mouse.scroll(int(params["amount"]))
        else:
            raise ValueError(f"Unknown macro action: {step.action}")


def steps_to_json(steps: list[MacroStep]) -> str:
    """Serialize macro steps to JSON."""
    return json.dumps([step.to_dict() for step in steps], indent=2)


def steps_from_json(data: str) -> list[MacroStep]:
    """Deserialize macro steps from JSON."""
    return [MacroStep.from_dict(entry) for entry in json.loads(data)]
