from __future__ import annotations

from app.input.keyboard_service import KeyboardService


class FakeController:
    def __init__(self) -> None:
        self.pressed: list[str] = []
        self.held: list[str] = []
        self.released: list[str] = []
        self.typed = ""
        self.hotkeys: list[tuple[str, ...]] = []

    def press(self, key: str) -> None:
        self.pressed.append(key)

    def keyDown(self, key: str) -> None:
        self.held.append(key)

    def keyUp(self, key: str) -> None:
        self.released.append(key)

    def hotkey(self, *keys: str) -> None:
        self.hotkeys.append(keys)

    def write(self, text: str, interval: float = 0.0) -> None:
        self.typed += text


def test_press_and_hold_release() -> None:
    controller = FakeController()
    service = KeyboardService(controller=controller)

    service.press("a")
    service.hold("shift")
    service.release("shift")

    assert controller.pressed == ["a"]
    assert controller.held == ["shift"]
    assert controller.released == ["shift"]


def test_hotkey_and_write() -> None:
    controller = FakeController()
    service = KeyboardService(controller=controller)

    service.hotkey("ctrl", "c")
    service.write("hello")

    assert controller.hotkeys == [("ctrl", "c")]
    assert controller.typed == "hello"
