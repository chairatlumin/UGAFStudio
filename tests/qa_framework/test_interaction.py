from __future__ import annotations

from typing import Any

import pytest

from qa_framework.gameplay.interaction import execute_actions
from qa_framework.gameplay.suite import load_run_config


class FakeInput:
    def __init__(self) -> None:
        self.events: list[tuple[Any, ...]] = []

    def press(self, key: str) -> None:
        self.events.append(("press", key))

    def hold(self, key: str) -> None:
        self.events.append(("hold", key))

    def release(self, key: str) -> None:
        self.events.append(("release", key))

    def move(self, dx: int, dy: int) -> None:
        self.events.append(("look", dx, dy))

    def click(self, x: int | None = None, y: int | None = None) -> None:
        self.events.append(("click", x, y))

    def release_all(self) -> None:
        self.events.append(("release_all",))


def test_actions_cover_menu_lobby_interact_and_movement(tmp_path) -> None:
    suite = tmp_path / "interaction.json"
    suite.write_text(
        '{"actions": ['
        '{"action":"press","key":"enter"},'
        '{"action":"wait","seconds":0},'
        '{"action":"interact"},'
        '{"action":"move","direction":"forward","seconds":0},'
        '{"action":"look","dx":120,"dy":-10}'
        "]}",
        encoding="utf-8",
    )
    config = load_run_config(suite)
    fake = FakeInput()

    results = execute_actions(config.actions, fake, sleep=lambda _seconds: None)

    assert all(result.passed for result in results)
    assert fake.events == [
        ("press", "enter"),
        ("press", "e"),
        ("hold", "w"),
        ("release", "w"),
        ("look", 120, -10),
        ("release_all",),
    ]


def test_wait_for_requires_capture_and_assertion_services() -> None:
    with pytest.raises(ValueError, match="wait_for requires"):
        execute_actions([{"action": "wait_for", "assertion": {}}], FakeInput())
