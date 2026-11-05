"""Tests for CapturingRecorder (capture-to-macro bridge)."""

from __future__ import annotations

from app.automation.macro import MacroRecorder
from app.automation.macro_recorder import CapturingRecorder


class TestCapturingRecorder:
    def test_key_press_recorded_as_key_step(self) -> None:
        recorder = MacroRecorder()
        bridge = CapturingRecorder(recorder)
        recorder.start()

        bridge.on_key_press("a")
        bridge.on_key_press("enter")

        steps = recorder.stop()
        assert len(steps) == 2
        assert steps[0].action == "key"
        assert steps[0].params == {"key": "a"}
        assert steps[1].action == "key"
        assert steps[1].params == {"key": "enter"}

    def test_key_release_ignored(self) -> None:
        recorder = MacroRecorder()
        bridge = CapturingRecorder(recorder)
        recorder.start()

        bridge.on_key_release("a")

        steps = recorder.stop()
        assert len(steps) == 0

    def test_mouse_click_recorded_when_pressed(self) -> None:
        recorder = MacroRecorder()
        bridge = CapturingRecorder(recorder)
        recorder.start()

        bridge.on_mouse_click(100, 200, "left", True)
        bridge.on_mouse_click(150, 250, "right", True)

        steps = recorder.stop()
        assert len(steps) == 2
        assert steps[0].action == "click"
        assert steps[0].params == {"x": 100, "y": 200, "button": "left"}
        assert steps[1].action == "click"
        assert steps[1].params == {"x": 150, "y": 250, "button": "right"}

    def test_mouse_click_ignored_when_released(self) -> None:
        recorder = MacroRecorder()
        bridge = CapturingRecorder(recorder)
        recorder.start()

        bridge.on_mouse_click(100, 200, "left", False)

        steps = recorder.stop()
        assert len(steps) == 0

    def test_scroll_recorded_as_scroll_step(self) -> None:
        recorder = MacroRecorder()
        bridge = CapturingRecorder(recorder)
        recorder.start()

        bridge.on_mouse_scroll(0, 0, 0, 1)
        bridge.on_mouse_scroll(0, 0, 0, -1)

        steps = recorder.stop()
        assert len(steps) == 2
        assert steps[0].action == "scroll"
        assert steps[0].params == {"amount": 1}
        assert steps[1].action == "scroll"
        assert steps[1].params == {"amount": -1}

    def test_mouse_move_filtered_by_default(self) -> None:
        recorder = MacroRecorder()
        bridge = CapturingRecorder(recorder)
        recorder.start()

        bridge.on_mouse_move(10, 10)
        bridge.on_mouse_move(15, 15)  # below threshold

        steps = recorder.stop()
        assert len(steps) == 0

    def test_mouse_move_captured_when_enabled(self) -> None:
        recorder = MacroRecorder()
        bridge = CapturingRecorder(recorder, capture_mouse_move=True)
        recorder.start()

        bridge.on_mouse_move(10, 10)
        bridge.on_mouse_move(100, 100)  # above threshold

        steps = recorder.stop()
        assert len(steps) == 2
        assert steps[0].action == "move"
        assert steps[0].params == {"x": 10, "y": 10}
        assert steps[1].action == "move"
        assert steps[1].params == {"x": 100, "y": 100}

    def test_mouse_move_threshold_filters_small_movements(self) -> None:
        recorder = MacroRecorder()
        bridge = CapturingRecorder(recorder, capture_mouse_move=True, mouse_move_threshold=50)
        recorder.start()

        bridge.on_mouse_move(0, 0)
        bridge.on_mouse_move(10, 10)  # below threshold
        bridge.on_mouse_move(100, 100)  # above threshold from last

        steps = recorder.stop()
        assert len(steps) == 2
        assert steps[0].params == {"x": 0, "y": 0}
        assert steps[1].params == {"x": 100, "y": 100}
