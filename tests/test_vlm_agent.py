from __future__ import annotations

import json

import numpy as np

from qa_framework.gameplay_agent.backends import EchoVLMBackend
from qa_framework.gameplay_agent.vlm_agent import VLMAgent


def test_echo_backend_return_expected_action() -> None:
    """EchoVLMBackend returns the action specified in its response."""
    response = json.dumps({"action": "key_press", "params": {"key": "w"}})
    backend = EchoVLMBackend(response=response)
    agent = VLMAgent(
        backend=backend,
        allowed_actions=["key_press", "mouse_move", "click"],
    )
    frame = np.array([[1, 2, 3]], dtype="uint8")
    action = agent.decide(frame)
    assert action.action == "key_press"
    assert action.params == {"key": "w"}


def test_malformed_json_fails_closed_to_noop() -> None:
    """Malformed output never guesses an input action."""
    backend = EchoVLMBackend(response="garbage")
    agent = VLMAgent(
        backend=backend,
        allowed_actions=["key_press", "mouse_move", "click"],
    )
    frame = np.array([[1, 2, 3]], dtype="uint8")
    for _ in range(3):
        action = agent.decide(frame)
        assert action.action == "noop"
        assert agent.consecutive_fallbacks == _ + 1


def test_invalid_or_out_of_frame_actions_fail_closed() -> None:
    for response in (
        {"action": "launch_shell", "params": {}},
        {"action": "key_press", "params": {}},
        {"action": "key_press", "params": {"key": "f12"}},
        {"action": "mouse_move", "params": {"x": 1000, "y": 3}},
        {"action": "click", "params": {"button": "left", "x": 2}},
        {"action": "noop", "params": {"unexpected": True}},
    ):
        agent = VLMAgent(
            backend=EchoVLMBackend(response=json.dumps(response)),
            allowed_actions=["key_press", "mouse_move", "click", "noop"],
        )
        action = agent.decide(np.zeros((8, 8, 3), dtype="uint8"))
        assert action.action == "noop"
        assert agent.consecutive_fallbacks == 1


def test_backend_error_fails_closed_to_noop() -> None:
    class BrokenBackend:
        def complete(self, prompt: str, image: np.ndarray) -> str:
            raise TimeoutError("backend timed out")

    agent = VLMAgent(BrokenBackend(), ["key_press", "noop"])
    action = agent.decide(np.zeros((8, 8, 3), dtype="uint8"))
    assert action.action == "noop"
    assert agent.consecutive_fallbacks == 1


def test_history_bounded_to_max_history() -> None:
    """History is bounded by max_history; oldest entries are dropped."""
    backend = EchoVLMBackend(response=json.dumps({"action": "key_press", "params": {"key": "w"}}))
    agent = VLMAgent(
        backend=backend,
        allowed_actions=["key_press", "mouse_move", "click"],
        max_history=3,
    )
    frame = np.array([[1, 2, 3]], dtype="uint8")
    # Decide 5 times
    for _ in range(5):
        agent.decide(frame)
    # History should only contain the last 3 entries
    assert len(agent._history) <= 3, f"History length {len(agent._history)} exceeds max_history=3"


def test_prompt_contains_allowed_actions_and_system_instructions() -> None:
    """The prompt built by decide() includes allowed actions and system instructions."""
    system_prompt = "You are a QA agent."
    backend = EchoVLMBackend(response=json.dumps({"action": "key_press", "params": {"key": "w"}}))
    agent = VLMAgent(
        backend=backend,
        allowed_actions=["key_press", "release", "click"],
        system_prompt=system_prompt,
        max_history=5,
    )
    frame = np.array([[1, 2, 3]], dtype="uint8")
    agent.decide(frame)
    # History should have been recorded
    assert len(agent._history) >= 1


def test_decide_with_context_includes_it_in_prompt() -> None:
    """decide() with context kwarg appends it to the prompt sent to the backend."""
    backend = EchoVLMBackend(response=json.dumps({"action": "key_press", "params": {"key": "w"}}))
    agent = VLMAgent(
        backend=backend,
        allowed_actions=["key_press", "mouse_move", "click"],
    )
    frame = np.array([[1, 2, 3]], dtype="uint8")
    ctx = 'OCR detected text on screen:\n  "HP" at (10,20)\n  "Mana" at (30,40)'
    agent.decide(frame, context=ctx)
    assert len(backend._prompts) == 1
    assert ctx in backend._prompts[0]


def test_decide_without_context_omits_context() -> None:
    """decide() without context does not append any context section."""
    backend = EchoVLMBackend(response=json.dumps({"action": "noop", "params": {}}))
    agent = VLMAgent(
        backend=backend,
        allowed_actions=["noop"],
    )
    frame = np.array([[1, 2, 3]], dtype="uint8")
    agent.decide(frame)
    assert len(backend._prompts) == 1
    assert "OCR detected" not in backend._prompts[0]


def test_learn_appends_reward_info() -> None:
    """learn() appends reward info to the internal episode log."""
    backend = EchoVLMBackend(response=json.dumps({"action": "key_press", "params": {"key": "w"}}))
    agent = VLMAgent(
        backend=backend,
        allowed_actions=["key_press"],
    )
    frame = np.array([[1, 2, 3]], dtype="uint8")
    agent.decide(frame)
    agent.learn(reward=1.0, done=False)
    agent.learn(reward=0.5, done=True)
    assert len(agent._episode_log) == 2
    assert agent._episode_log[0] == {"reward": 1.0, "done": False}
    assert agent._episode_log[1] == {"reward": 0.5, "done": True}
