from __future__ import annotations

from pathlib import Path

import numpy as np

from qa_framework.gameplay.bot import run_bot_episode
from qa_framework.gameplay.suite import load_run_config
from qa_framework.gameplay_agent.actions import Action
from qa_framework.gameplay_agent.base import GameplayAgent


class FakeController:
    def __init__(self) -> None:
        self.events: list[tuple[str, str]] = []
        self.released = False

    def press(self, key: str) -> None:
        self.events.append(("press", key))

    def hold(self, key: str) -> None:
        self.events.append(("hold", key))

    def release(self, key: str) -> None:
        self.events.append(("release", key))

    def move(self, dx: int, dy: int) -> None:
        self.events.append(("move", f"{dx},{dy}"))

    def click(self, x: int | None = None, y: int | None = None) -> None:
        self.events.append(("click", f"{x},{y}"))

    def release_all(self) -> None:
        self.released = True


class FakeAgent(GameplayAgent):
    def __init__(self) -> None:
        self.observed = 0
        self.learned: list[tuple[float, bool]] = []

    def observe(self, frame: np.ndarray) -> np.ndarray:
        self.observed += 1
        return frame

    def decide(self, observation: np.ndarray) -> Action:
        return Action("press", {"key": "space"})

    def learn(self, reward: float, done: bool) -> None:
        self.learned.append((reward, done))


def test_bot_episode_records_actions_rewards_and_releases_input() -> None:
    agent = FakeAgent()
    controller = FakeController()
    frame = np.zeros((8, 8, 3), dtype=np.uint8)
    frames = iter([frame, frame, frame, frame])

    summary = run_bot_episode(
        agent,
        lambda: next(frames),
        controller,  # type: ignore[arg-type]
        max_steps=2,
        step_interval=0,
    )

    assert summary.passed
    assert summary.steps == 2
    assert summary.actions == ["press", "press"]
    assert len(summary.rewards) == 2
    assert agent.observed == 2
    assert len(agent.learned) == 2
    assert controller.events == [("press", "space"), ("press", "space")]
    assert controller.released


def test_gameplay_suite_loads_bot_settings(tmp_path: Path) -> None:
    suite = tmp_path / "bot.json"
    suite.write_text(
        '{"bot": {"enabled": true, "max_steps": 4, "step_interval": 0, '
        '"actions": [{"action": "press", "key": "space"}]}}',
        encoding="utf-8",
    )

    config = load_run_config(suite)

    assert config.bot_enabled
    assert config.bot_max_steps == 4
    assert config.bot_step_interval == 0
    assert config.bot_actions == [{"action": "press", "key": "space"}]
