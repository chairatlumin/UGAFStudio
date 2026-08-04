from __future__ import annotations

import sys
from types import ModuleType
from typing import Any

from app.input.hotkey_service import HotkeyService


class FakeKeyboard(ModuleType):
    def __init__(self) -> None:
        super().__init__("keyboard")
        self.hotkeys: dict[int, str] = {}
        self._next = 0

    def add_hotkey(self, hotkey: str, callback: Any) -> int:
        self._next += 1
        self.hotkeys[self._next] = hotkey
        return self._next

    def remove_hotkey(self, handle: Any) -> None:
        self.hotkeys.pop(handle, None)


def test_register_adds_hotkey(monkeypatch: Any) -> None:
    fake = FakeKeyboard()
    monkeypatch.setitem(sys.modules, "keyboard", fake)

    service = HotkeyService()
    called = []

    ok = service.register("ctrl+shift+p", lambda: called.append(1))

    assert ok
    assert len(fake.hotkeys) == 1


def test_unregister_all_removes_hotkeys(monkeypatch: Any) -> None:
    fake = FakeKeyboard()
    monkeypatch.setitem(sys.modules, "keyboard", fake)

    service = HotkeyService()
    service.register("ctrl+a", lambda: None)

    service.unregister_all()

    assert len(fake.hotkeys) == 0


def test_register_returns_false_when_unavailable() -> None:
    service = HotkeyService()
    service._keyboard = None
    service.available = lambda: False  # type: ignore[method-assign]

    assert service.register("ctrl+a", lambda: None) is False
