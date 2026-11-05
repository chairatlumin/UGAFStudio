from __future__ import annotations

from pathlib import Path
from typing import cast

import numpy as np

from qa_framework.gameplay_agent.actions import Action, ActionExecutor
from qa_framework.gameplay_agent.moa import MOAAgent
from qa_framework.gameplay_agent.reward import FrameDiffReward
from qa_framework.gameplay_agent.skill_cache import SkillCache
from qa_framework.gameplay_agent.vlm_agent import VLMAgent
from scripts.live_gameplay_agent import LiveGameplayAgent


class _MockMOAAgent(MOAAgent):
    """A MOAAgent stand-in that records ``update_rewards`` invocations.

    It is a real subclass of :class:`MOAAgent` (so ``isinstance(...)`` is True)
    but overrides the decision hooks to avoid any backend work. The
    ``early_exit`` flag is exposed to mirror the live construction path.
    """

    def __init__(self, *, early_exit: bool = True) -> None:
        self._early_exit = early_exit
        self._consecutive_fallbacks = 0
        self.last_decision_succeeded = True
        self.update_rewards_calls: list[dict[str, float]] = []
        self.decided_action = Action(action="key_press", params={"key": "w"})

    @property
    def consecutive_fallbacks(self) -> int:
        return self._consecutive_fallbacks

    def observe(self, frame: object) -> object:
        return frame

    def decide(self, *args: object, **kwargs: object) -> Action:
        return self.decided_action

    def learn(self, reward: float, done: bool) -> None:  # noqa: D401 - test stub
        pass

    def update_rewards(self, signature_to_reward: dict[str, float]) -> None:
        self.update_rewards_calls.append(dict(signature_to_reward))


def _build_live(agent: MOAAgent, tmp_path: Path) -> LiveGameplayAgent:
    cache = SkillCache(path=tmp_path / "skills.json")
    return LiveGameplayAgent(
        agent=agent,
        cache=cache,
        executor=cast("ActionExecutor", _RecordingExecutor()),
        reward_fn=FrameDiffReward(),
        window_rect=(0, 0, 100, 100),
        menu_keywords=frozenset(),
        win_w=100,
        win_h=100,
        trace_path=tmp_path / "trace.jsonl",
    )


class _RecordingExecutor:
    def __init__(self) -> None:
        self.dispatched: list[Action] = []

    def dispatch(self, action: Action) -> None:
        self.dispatched.append(action)


def test_moa_agent_constructs_with_early_exit(tmp_path: Path) -> None:
    """The live MOA branch must construct with early_exit=True + min_votes=1.

    Mirrors the construction in ``main()`` (MOA branch) without requiring a
    game window: a real MOAAgent with a stub sub-agent and the same kwargs.
    """
    sub = cast("VLMAgent", _StubSubAgent())
    agent = MOAAgent([sub], weights=[1.0], early_exit=True, min_votes=1)
    assert agent._early_exit is True
    assert agent._min_votes == 1


def test_moa_from_backends_early_exit_matches_live_branch(tmp_path: Path) -> None:
    """MOAAgent.from_backends (the live main() path) yields early_exit + weights.

    Confirms the DRY factory path used by ``main()`` produces the same MOA shape
    as the explicit construction: early_exit=True, min_votes=1, weights from specs.
    """
    specs = [
        ("qwen/qwen2.5-vl-7b", 1.0),
        ("google/gemma-4-e2b", 0.6),
        ("qwen/qwen3.8-27b", 0.4),
    ]

    def _factory(model: str) -> "object":
        return _StubSubAgent()

    agent = MOAAgent.from_backends(
        backend_factory=_factory,  # type: ignore[arg-type]
        specs=specs,
        allowed_actions=["noop"],
        early_exit=True,
        min_votes=1,
    )
    assert agent._early_exit is True
    assert agent._min_votes == 1
    assert agent._weights == [1.0, 0.6, 0.4]
    assert len(agent._agents) == 3


class _StubSubAgent:
    """Minimal stand-in for a VLMAgent sub-agent (no backend needed)."""

    def __init__(self) -> None:
        self._consecutive_fallbacks = 0

    @property
    def consecutive_fallbacks(self) -> int:
        return self._consecutive_fallbacks

    def observe(self, frame: object) -> object:
        return frame

    def decide(self, *args: object, **kwargs: object) -> Action:
        return Action(action="noop", params={})

    def learn(self, reward: float, done: bool) -> None:  # noqa: D401
        pass


def test_moa_update_rewards_called_during_step(tmp_path: Path) -> None:
    """When the agent is an MOAAgent, step() feeds the frame-diff reward back."""
    from qa_framework.gameplay_agent.moa import _action_signature

    agent = _MockMOAAgent(early_exit=True)
    live = _build_live(agent, tmp_path)

    ocr_words = [{"text": "menu", "x": 10, "y": 20, "w": 30, "h": 10}]
    frame = np.full((16, 16, 3), 128, dtype=np.uint8)

    live.step(frame, ocr_words, frame)

    assert len(agent.update_rewards_calls) == 1
    # The dispatched action was a key_press of 'w'.
    sig = _action_signature(Action(action="key_press", params={"key": "w"}))
    assert sig in agent.update_rewards_calls[0]
    # Frame unchanged -> reward 0.0
    assert agent.update_rewards_calls[0][sig] == 0.0


def test_non_moa_agent_not_fed_rewards(tmp_path: Path) -> None:
    """A plain VLMAgent-shaped agent does not trigger reward weighting."""
    cache = SkillCache(path=tmp_path / "skills.json")
    agent = _PlainAgent()
    live = LiveGameplayAgent(
        agent=cast("VLMAgent | MOAAgent", agent),
        cache=cache,
        executor=cast("ActionExecutor", _RecordingExecutor()),
        reward_fn=FrameDiffReward(),
        window_rect=(0, 0, 100, 100),
        menu_keywords=frozenset(),
        win_w=100,
        win_h=100,
        trace_path=tmp_path / "trace.jsonl",
    )
    frame = np.full((16, 16, 3), 128, dtype=np.uint8)
    live.step(frame, [], frame)
    assert agent.learn_called is True  # learn still invoked
    # no assertion beyond learn; just confirms no MOA path crashes


def test_moa_failure_skips_input_and_halts_after_limit(tmp_path: Path) -> None:
    """A failed MOA decision sends no input and repeated failures halt safely."""
    agent = _MockMOAAgent(early_exit=True)
    live = _build_live(agent, tmp_path)
    frame = np.full((16, 16, 3), 128, dtype=np.uint8)

    # A real vote succeeded -> flag True -> no back-off path taken.
    agent.last_decision_succeeded = True
    live.step(frame, [], frame)
    # No exception, decision treated as successful.
    assert agent.last_decision_succeeded is True

    executor = live._executor
    dispatched_before = len(executor.dispatched)  # type: ignore[attr-defined]
    agent.last_decision_succeeded = False
    for _ in range(3):
        live.step(frame, [], frame)
    assert len(executor.dispatched) == dispatched_before  # type: ignore[attr-defined]
    assert live.halted is True


class _PlainAgent:
    """Mimics a VLMAgent (not an MOAAgent) for the negative case."""

    def __init__(self) -> None:
        self._consecutive_fallbacks = 0
        self.learn_called = False

    @property
    def consecutive_fallbacks(self) -> int:
        return self._consecutive_fallbacks

    def observe(self, frame: object) -> object:
        return frame

    def decide(self, *args: object, **kwargs: object) -> Action:
        return Action(action="key_press", params={"key": "w"})

    def learn(self, reward: float, done: bool) -> None:
        self.learn_called = True
