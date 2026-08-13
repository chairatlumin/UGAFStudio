from __future__ import annotations

import sys
from types import ModuleType
from typing import Any

from app.input.gamepad_service import GamepadService, GamepadState


class FakeEvent:
    def __init__(self, code: str, state: Any) -> None:
        self.code = code
        self.state = state


class FakeInputs(ModuleType):
    def __init__(self, events: list[FakeEvent]) -> None:
        super().__init__("inputs")
        self.events = events

    def get_gamepad(self, timeout: float) -> list[FakeEvent]:
        return self.events


def test_poll_maps_buttons_and_axes(monkeypatch: Any) -> None:
    fake = FakeInputs(
        [
            FakeEvent("BTN_SOUTH", 1),
            FakeEvent("ABS_X", 32767),
            FakeEvent("ABS_Z", 127),
        ]
    )
    monkeypatch.setitem(sys.modules, "inputs", fake)

    state = GamepadService().poll()

    assert state.buttons["BTN_SOUTH"] is True
    assert state.axes["ABS_X"] == 1.0
    assert state.axes["ABS_Z"] == round(127 / 255.0, 4)


def test_poll_returns_empty_when_unavailable() -> None:
    service = GamepadService()

    state = service.poll()

    assert isinstance(state, GamepadState)
    assert state.buttons == {}
