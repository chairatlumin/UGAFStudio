"""Engine-neutral autonomous gameplay episodes for QA.

The bot loop only depends on a frame capture callable, a gameplay agent, and
the small input-controller protocol. Engine-specific launch and window code
stays outside this module, so the same episode runner can drive any game that
can expose those three capabilities.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable

import numpy as np

from qa_framework.gameplay_agent.actions import Action
from qa_framework.gameplay_agent.base import GameplayAgent
from qa_framework.gameplay_agent.reward import FrameDiffReward

from .interaction import InputController


@dataclass
class BotRunSummary:
    """Auditable outcome of one autonomous gameplay episode."""

    enabled: bool = False
    steps: int = 0
    actions: list[str] = field(default_factory=list)
    rewards: list[float] = field(default_factory=list)
    passed: bool = True
    error: str | None = None


def run_bot_episode(
    agent: GameplayAgent,
    capture: Callable[[], np.ndarray],
    controller: InputController,
    *,
    max_steps: int = 20,
    step_interval: float = 0.25,
    reward: FrameDiffReward | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> BotRunSummary:
    """Run a bounded observe-decide-act-learn loop and record every action.

    Failures stop the episode and are returned in the summary so the caller can
    include them in the normal QA report. The controller releases held keys in
    a ``finally`` block, including when an agent or capture backend fails.
    """
    summary = BotRunSummary(enabled=True)
    reward_tracker = reward or FrameDiffReward()
    try:
        for _ in range(max(0, max_steps)):
            frame = capture()
            observation = agent.observe(frame)
            action = agent.decide(observation)
            _dispatch_action(action, controller)
            summary.steps += 1
            summary.actions.append(action.action)

            next_frame = capture()
            value = reward_tracker.update(next_frame)
            summary.rewards.append(value)
            agent.learn(value, done=False)
            if step_interval > 0:
                sleep(step_interval)
    except Exception as exc:  # noqa: BLE001 - surface bot failure in QA output
        summary.passed = False
        summary.error = str(exc)
        try:
            agent.learn(0.0, done=True)
        except Exception:
            pass
    finally:
        release_all = getattr(controller, "release_all", None)
        if callable(release_all):
            release_all()
    return summary


def _dispatch_action(action: Action, controller: InputController) -> None:
    """Translate the shared agent action schema to the input protocol."""
    params = action.params or {}
    if action.action in {"key_press", "press", "interact"}:
        controller.press(str(params.get("key", "e" if action.action == "interact" else "")))
    elif action.action in {"key_hold", "hold"}:
        controller.hold(str(params["key"]))
    elif action.action in {"key_release", "release"}:
        controller.release(str(params["key"]))
    elif action.action in {"mouse_move", "look"}:
        controller.move(
            int(params.get("dx", params.get("x", 0))), int(params.get("dy", params.get("y", 0)))
        )
    elif action.action == "click":
        controller.click(params.get("x"), params.get("y"))
    elif action.action == "noop":
        return
    elif action.action == "type_text":
        type_text = getattr(controller, "type_text", None)
        if not callable(type_text):
            raise ValueError("The selected input controller does not support type_text")
        type_text(str(params.get("text", "")))
    else:
        raise ValueError(f"Unsupported bot action: {action.action!r}")
