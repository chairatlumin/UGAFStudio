from __future__ import annotations

from app.automation.macro import (
    MacroPlayer,
    MacroRecorder,
    MacroStep,
    steps_from_json,
    steps_to_json,
)
from app.input.keyboard_service import KeyboardService
from app.input.mouse_service import MouseService
from tests.input.test_keyboard_service import FakeController as FakeKeyboardController
from tests.input.test_mouse_service import FakeController as FakeMouseController


def make_services() -> tuple[
    MouseService, KeyboardService, FakeMouseController, FakeKeyboardController
]:
    mouse_controller = FakeMouseController()
    keyboard_controller = FakeKeyboardController()
    return (
        MouseService(controller=mouse_controller),
        KeyboardService(controller=keyboard_controller),
        mouse_controller,
        keyboard_controller,
    )


def test_recorder_captures_ordered_steps() -> None:
    times = iter([0.0, 0.5, 1.0])
    recorder = MacroRecorder(clock=lambda: next(times))

    recorder.start()
    recorder.record_move(10, 20)
    recorder.record_click(30, 40)
    steps = recorder.stop()

    assert recorder.recording is False
    assert len(steps) == 2
    assert steps[0].action == "move"
    assert steps[0].delay_ms == 0.0
    assert steps[1].action == "click"
    assert steps[1].delay_ms == 500.0


def test_recorder_ignores_records_when_not_recording() -> None:
    recorder = MacroRecorder()

    recorder.record_move(1, 2)

    assert recorder.stop() == []


def test_player_dispatches_actions() -> None:
    mouse, keyboard, mouse_controller, keyboard_controller = make_services()

    steps = [
        MacroStep("move", {"x": 5, "y": 6}, delay_ms=0.0),
        MacroStep("click", {"x": 7, "y": 8, "button": "right"}, delay_ms=0.0),
        MacroStep("key", {"key": "a"}, delay_ms=0.0),
        MacroStep("write", {"text": "hi"}, delay_ms=0.0),
        MacroStep("scroll", {"amount": -1}, delay_ms=0.0),
    ]

    MacroPlayer(mouse=mouse, keyboard=keyboard, sleep=lambda _: None).play(steps)

    assert mouse_controller.moves[0][:2] == (5, 6)
    assert mouse_controller.clicks == [(7, 8, "right", 1)]
    assert mouse_controller.scrolls == [-1]
    assert keyboard_controller.pressed == ["a"]
    assert keyboard_controller.typed == "hi"


def test_player_rejects_unknown_action() -> None:
    mouse, keyboard, _, _ = make_services()

    steps = [MacroStep("fly", {})]

    try:
        MacroPlayer(mouse=mouse, keyboard=keyboard, sleep=lambda _: None).play(steps)
    except ValueError:
        return

    raise AssertionError("Expected ValueError for unknown action")


def test_steps_serialize_round_trip() -> None:
    steps = [MacroStep("move", {"x": 1, "y": 2}, delay_ms=3.5)]

    restored = steps_from_json(steps_to_json(steps))

    assert restored == steps
