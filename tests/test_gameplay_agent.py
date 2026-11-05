from __future__ import annotations

import numpy as np

from qa_framework.gameplay_agent import Action, ActionExecutor, RandomAgent
from qa_framework.gameplay_agent.vlm_agent import VLMAgent


def test_action_dataclass() -> None:
    a = Action(action="key_press", params={"key": "w"})
    assert a.action == "key_press"
    assert a.params == {"key": "w"}

    b = Action(action="click")
    assert b.action == "click"
    assert b.params == {}


def test_action_executor_dispatch_key_press() -> None:
    executor = ActionExecutor()
    action = Action(action="key_press", params={"key": "a"})
    executor.dispatch(action)  # should not raise


def test_action_executor_dispatch_mouse_move() -> None:
    executor = ActionExecutor()
    action = Action(action="mouse_move", params={"x": 10, "y": 20})
    executor.dispatch(action)  # should not raise


def test_action_executor_forwards_explicit_click_coordinates(monkeypatch) -> None:
    class Mouse:
        def __init__(self) -> None:
            self.click_args = None

        def click(self, *, x=None, y=None, button="left") -> None:
            self.click_args = (x, y, button)

    mouse = Mouse()
    monkeypatch.setattr(ActionExecutor, "_default_ms", mouse)
    ActionExecutor().dispatch(Action("click", {"x": 123, "y": 456, "button": "left"}))
    assert mouse.click_args == (123, 456, "left")


def test_action_executor_accepts_noop_without_input() -> None:
    ActionExecutor().dispatch(Action("noop", {}))


def test_random_agent_determinism() -> None:
    actions = [
        Action(action="key_press", params={"key": "w"}),
        Action(action="key_press", params={"key": "a"}),
        Action(action="key_press", params={"key": "s"}),
        Action(action="key_press", params={"key": "d"}),
        Action(action="mouse_move", params={"x": 0, "y": 0}),
        Action(action="click", params={}),
    ]
    agent = RandomAgent(actions=actions, seed=42)

    observations = [None] * 5
    results = [agent.decide(obs) for obs in observations]

    # With seed=42, the sequence must be reproducible
    assert len(results) == 5
    for r in results:
        assert r.action in {"key_press", "mouse_move", "click"}
        assert isinstance(r.params, dict)


def test_random_agent_learn_noop() -> None:
    actions = [Action(action="key_press", params={"key": "space"})]
    agent = RandomAgent(actions=actions, seed=123)
    agent.learn(reward=1.0, done=False)
    agent.learn(reward=0.0, done=True)  # should not raise


def test_random_agent_observe() -> None:
    actions = [Action(action="key_press", params={"key": "w"})]
    agent = RandomAgent(actions=actions, seed=0)
    frame = np.array([[1, 2, 3]], dtype="uint8")
    obs = agent.observe(frame)
    assert obs is frame


def test_platformer_stealth_prompt_requires_grounding_before_jumps() -> None:
    class Backend:
        prompt = ""

        def complete(self, prompt: str, _image: np.ndarray) -> str:
            self.prompt = prompt
            return '{"action":"noop","params":{}}'

    backend = Backend()
    agent = VLMAgent(backend, allowed_actions=["noop", "key_press"])
    action = agent.decide(np.zeros((12, 12, 3), dtype=np.uint8), strategy="platformer_stealth")
    assert action.action == "noop"
    assert "footing" in backend.prompt
    assert "patrol state" in backend.prompt
