"""Tests for LiveCapture."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.automation.capture import LiveCapture, _button_to_string, _key_to_string


class FakePynputKey:
    def __init__(self, name: str | None = None, char: str | None = None) -> None:
        self.name = name
        self.char = char


class FakePynputButton:
    def __init__(self, name: str) -> None:
        self.name = name


class FakeKeyCode:
    def __init__(self, char: str | None) -> None:
        self.char = char


class FakeListener:
    def __init__(self, **kwargs) -> None:
        self._callbacks = kwargs
        self._started = False
        self._stopped = False

    def start(self) -> None:
        self._started = True

    def stop(self) -> None:
        self._stopped = True


class TestKeyToString:
    def test_special_key_returns_name(self) -> None:
        result = _key_to_string(FakePynputKey(name="ctrl"))
        assert result == "ctrl"

    def test_char_key_returns_char(self) -> None:
        result = _key_to_string(FakeKeyCode(char="a"))
        assert result == "a"

    def test_empty_char_returns_empty(self) -> None:
        result = _key_to_string(FakeKeyCode(char=None))
        assert result == ""

    def test_unknown_returns_empty(self) -> None:
        result = _key_to_string(object())
        assert result == ""


class TestButtonToString:
    def test_left_button(self) -> None:
        result = _button_to_string(FakePynputButton(name="left"))
        assert result == "left"

    def test_unknown_button(self) -> None:
        result = _button_to_string(object())
        assert result == "unknown"


class TestLiveCapture:
    def test_capture_starts_and_stops_without_error(self) -> None:
        capture = LiveCapture()
        fake_keyboard = MagicMock()
        fake_keyboard.Listener.return_value = FakeListener()
        fake_mouse = MagicMock()
        fake_mouse.Listener.return_value = FakeListener()

        with patch("pynput.keyboard") as kbd, patch("pynput.mouse") as mouse:
            kbd.Listener = fake_keyboard.Listener
            mouse.Listener = fake_mouse.Listener
            capture.start()
            assert capture.capturing is True
            capture.stop()
            assert capture.capturing is False

    def test_capture_forwards_events_to_listener(self) -> None:
        listener = MagicMock()
        capture = LiveCapture(listener=listener)

        capture._on_key_press(FakeKeyCode(char="a"))
        listener.on_key_press.assert_called_with("a")

        capture._on_key_release(FakeKeyCode(char="a"))
        listener.on_key_release.assert_called_with("a")

        capture._on_mouse_move(100, 200)
        listener.on_mouse_move.assert_called_with(100, 200)

        capture._on_mouse_click(50, 60, FakePynputButton(name="left"), True)
        listener.on_mouse_click.assert_called_with(50, 60, "left", True)

        capture._on_mouse_scroll(0, 0, 0, 1)
        listener.on_mouse_scroll.assert_called_with(0, 0, 0, 1)

    def test_set_listener_updates_listener(self) -> None:
        capture = LiveCapture()
        new_listener = MagicMock()
        capture.set_listener(new_listener)
        capture._on_key_press(FakeKeyCode(char="b"))
        new_listener.on_key_press.assert_called_with("b")

    def test_stop_when_not_capturing_is_noop(self) -> None:
        capture = LiveCapture()
        capture.stop()  # should not raise

    def test_start_when_already_capturing_is_noop(self) -> None:
        capture = LiveCapture()
        with patch("pynput.keyboard") as kbd, patch("pynput.mouse") as mouse:
            kbd.Listener = MagicMock(return_value=MagicMock())
            mouse.Listener = MagicMock(return_value=MagicMock())
            capture.start()
            capture.start()  # second call should be no-op
            assert capture.capturing is True
