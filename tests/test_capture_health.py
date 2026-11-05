from __future__ import annotations

from pathlib import Path
from typing import cast
from unittest.mock import MagicMock

import numpy as np

from qa_framework.gameplay_agent.actions import Action, ActionExecutor
from qa_framework.gameplay_agent.reward import FrameDiffReward
from qa_framework.gameplay_agent.skill_cache import SkillCache
from qa_framework.gameplay_agent.vlm_agent import VLMAgent
from scripts.live_gameplay_agent import LiveGameplayAgent, frame_health


def _black_frame() -> np.ndarray:
    return np.zeros((48, 64, 3), dtype=np.uint8)


def _normal_frame() -> np.ndarray:
    rng = np.random.default_rng(0)
    return rng.integers(0, 256, size=(48, 64, 3), dtype=np.uint8)


def _build_live(tmp_path: Path) -> LiveGameplayAgent:
    agent = MagicMock(spec=VLMAgent)
    agent.decide.return_value = Action(action="noop", params={})
    agent.consecutive_fallbacks = 0
    cache = SkillCache(path=tmp_path / "skills.json")
    executor = MagicMock(spec=ActionExecutor)
    return LiveGameplayAgent(
        agent=agent,
        cache=cache,
        executor=executor,
        reward_fn=FrameDiffReward(),
        window_rect=(0, 0, 100, 100),
        menu_keywords=frozenset(),
        win_w=100,
        win_h=100,
        trace_path=tmp_path / "trace.jsonl",
    )


def test_frame_health_black() -> None:
    h = frame_health(_black_frame())
    assert h["non_black_ratio"] == 0.0
    assert h["mean_brightness"] == 0.0


def test_frame_health_normal() -> None:
    h = frame_health(_normal_frame())
    assert h["non_black_ratio"] > 0.9


def test_frame_health_bounds_unique_color_work_to_a_sample(monkeypatch) -> None:
    original_unique = np.unique
    observed: list[int] = []

    def bounded_unique(values, *args, **kwargs):
        observed.append(values.size)
        assert values.ndim == 1
        assert values.size <= 16_384
        return original_unique(values, *args, **kwargs)

    monkeypatch.setattr("scripts.live_gameplay_agent.np.unique", bounded_unique)
    frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
    result = frame_health(frame)
    assert observed and observed[0] <= 16_384
    assert result["non_black_ratio"] == 0.0


def test_step_skips_black_frame(tmp_path: Path) -> None:
    live = _build_live(tmp_path)
    black = _black_frame()
    reward = live.step(black, [], black)
    assert reward == 0.0
    assert live._agent.decide.call_count == 0  # type: ignore[attr-defined]
    assert cast("MagicMock", live._executor).dispatch.call_count == 0  # type: ignore[attr-defined]

    normal = _normal_frame()
    live.step(normal, [], normal)
    assert live._agent.decide.call_count == 1  # type: ignore[attr-defined]


def test_step_freeze_logged_not_skipped(tmp_path: Path) -> None:
    live = _build_live(tmp_path)
    frame = _normal_frame()
    live.step(frame, [], frame)
    live.step(frame, [], frame)
    assert live._agent.decide.call_count == 2  # type: ignore[attr-defined]
