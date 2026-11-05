from __future__ import annotations

import json
import time
from unittest.mock import MagicMock

import numpy as np

from qa_framework.gameplay_agent.actions import Action
from qa_framework.gameplay_agent.backends import EchoVLMBackend, VLMBackend
from qa_framework.gameplay_agent.moa import MOAAgent, _action_signature, normalize_action
from qa_framework.gameplay_agent.vlm_agent import VLMAgent


def _agent(response: str) -> VLMAgent:
    return VLMAgent(
        backend=EchoVLMBackend(response=response),
        allowed_actions=["key_press", "mouse_move", "click", "noop"],
    )


def _frame() -> np.ndarray:
    return np.zeros((4, 4, 3), dtype="uint8")


def test_moa_majority_wins() -> None:
    """When two of three sub-agents agree, the majority action wins."""
    a0 = _agent(json.dumps({"action": "key_press", "params": {"key": "w"}}))
    a1 = _agent(json.dumps({"action": "key_press", "params": {"key": "w"}}))
    a2 = _agent(json.dumps({"action": "click", "params": {"button": "left"}}))

    moa = MOAAgent([a0, a1, a2])
    frame = _frame()
    winner = moa.decide("sig", [], frame, [])

    assert winner.action == "key_press"
    assert winner.params == {"key": "w"}
    # No backend errors when every sub-agent succeeds.
    assert moa.backend_errors == 0


def test_moa_tie_broken_by_weight() -> None:
    """On a weight tie, the action backed by the highest single model wins."""
    # a0 (weight 0.4) and a2 (weight 0.6) both vote key_press; a1 (1.0) votes click.
    a0 = _agent(json.dumps({"action": "key_press", "params": {"key": "w"}}))
    a1 = _agent(json.dumps({"action": "click", "params": {"button": "left"}}))
    a2 = _agent(json.dumps({"action": "key_press", "params": {"key": "w"}}))

    moa = MOAAgent([a0, a1, a2], weights=[0.4, 1.0, 0.6])
    frame = _frame()
    winner = moa.decide("sig", [], frame, [])

    # key_press and click both total weight 1.0 -> click wins via higher single-model weight.
    assert winner.action == "click"


def test_moa_all_fail_falls_back_to_first_agent() -> None:
    """If every sub-agent fails, MOA falls back to the first agent's action."""
    fallback = Action(action="noop", params={})

    a0 = MagicMock(spec=VLMAgent)
    a0.decide.side_effect = [Exception("boom-0"), fallback]
    a1 = MagicMock(spec=VLMAgent)
    a1.decide.side_effect = [Exception("boom-1")]
    a2 = MagicMock(spec=VLMAgent)
    a2.decide.side_effect = [Exception("boom-2")]

    moa = MOAAgent([a0, a1, a2])
    frame = _frame()
    winner = moa.decide("sig", [], frame, [])

    assert winner is fallback
    # Each of the three parallel failures is counted.
    assert moa.backend_errors == 3


def test_action_signature_is_stable() -> None:
    """Two equal actions share a signature; a param change yields a new one."""
    a = Action("click", {"button": "left"})
    b = Action("click", {"button": "left"})
    c = Action("click", {"button": "right"})
    assert _action_signature(a) == _action_signature(b)
    assert _action_signature(a) != _action_signature(c)


def test_moa_reward_weighting_shifts_winner() -> None:
    """A sub-agent whose action is consistently rewarded gains the vote."""
    # a0 (primary, w=0.4) votes key_press; a1 (w=1.0) votes click.
    # Baseline: click wins (1.0 > 0.4). After rewarding key_press heavily,
    # key_press's effective weight should overtake click.
    a0 = _agent(json.dumps({"action": "key_press", "params": {"key": "w"}}))
    a1 = _agent(json.dumps({"action": "click", "params": {"button": "left"}}))

    moa = MOAAgent([a0, a1], weights=[0.4, 1.0])
    frame = _frame()

    baseline = moa.decide("sig", [], frame, [])
    assert baseline.action == "click"

    # Feed a strong positive reward for the key_press signature.
    moa.update_rewards({_action_signature(Action("key_press", {"key": "w"})): 5.0})
    moa.update_rewards({_action_signature(Action("key_press", {"key": "w"})): 5.0})

    winner = moa.decide("sig2", [], frame, [])
    assert winner.action == "key_press"


def test_moa_early_exit_returns_without_slow_stragglers() -> None:
    """Early-exit MOA returns once primary+min_votes are in; slow agents don't block."""
    fast = _agent(json.dumps({"action": "key_press", "params": {"key": "w"}}))

    slow = MagicMock(spec=VLMAgent)

    def _slow(*_a: object, **_k: object) -> Action:
        time.sleep(3.0)  # simulate a slow vision model
        return Action("click", {"button": "left"})

    slow.decide.side_effect = _slow

    moa = MOAAgent([fast, slow], weights=[1.0, 0.6], early_exit=True, min_votes=1)
    frame = _frame()

    start = time.perf_counter()
    winner = moa.decide("sig", [], frame, [])
    elapsed = time.perf_counter() - start

    # The slow agent is still sleeping; early-exit must return quickly.
    assert elapsed < 2.0
    assert winner.action == "key_press"
    # A merely-slow model is NOT counted as a backend error.
    assert moa.backend_errors == 0


def test_moa_early_exit_counts_real_errors_only() -> None:
    """Early-exit still records a genuine backend failure when it is settled.

    Here the *primary* (index 0) sub-agent is the broken one, so it is resolved
    in the foreground before the trigger fires and its error is counted. A slow
    secondary is abandoned (not counted) — which is correct early-exit behavior.
    """
    broken = MagicMock(spec=VLMAgent)
    broken.decide.side_effect = RuntimeError("boom")
    fast = _agent(json.dumps({"action": "key_press", "params": {"key": "w"}}))

    moa = MOAAgent([broken, fast], weights=[0.6, 1.0], early_exit=True, min_votes=1)
    frame = _frame()
    winner = moa.decide("sig", [], frame, [])
    assert winner.action == "key_press"
    assert moa.backend_errors == 1


def test_moa_early_exit_no_double_count() -> None:
    """Early-exit returns fast on the majority and abandons slow sub-agents.

    With no background drain thread, a slow sub-agent's future is simply
    abandoned once the trigger (primary + min_votes) fires; it can never be
    re-counted as an error, and early-exit must not block on the slow model.
    """
    fast = _agent(json.dumps({"action": "key_press", "params": {"key": "w"}}))
    slow = MagicMock(spec=VLMAgent)

    def _slow(*_a: object, **_k: object) -> Action:
        time.sleep(2.0)
        return Action("click", {"button": "left"})

    slow.decide.side_effect = _slow

    moa = MOAAgent([fast, slow], weights=[1.0, 0.6], early_exit=True, min_votes=1)
    frame = _frame()
    start = time.perf_counter()
    winner = moa.decide("sig", [], frame, [])
    elapsed = time.perf_counter() - start

    assert winner.action == "key_press"
    # Returned before the 2.0s slow model finished.
    assert elapsed < 1.0
    # No error counted (the slow agent never errored; it was abandoned).
    assert moa.backend_errors == 0


def test_moa_from_backends_uses_factory() -> None:
    """from_backends builds sub-agents via the supplied backend factory."""
    made: list[str] = []

    def _factory(model: str) -> VLMBackend:
        made.append(model)
        return EchoVLMBackend(response=json.dumps({"action": "noop", "params": {}}))

    specs = [("qwen/qwen2.5-vl-7b", 1.0), ("google/gemma-4-e2b", 0.6)]
    moa = MOAAgent.from_backends(
        backend_factory=_factory,
        specs=specs,
        allowed_actions=["noop"],
    )
    assert made == ["qwen/qwen2.5-vl-7b", "google/gemma-4-e2b"]
    assert len(moa._agents) == 2
    assert moa._weights == [1.0, 0.6]


def test_moa_excludes_internal_subagent_fallback() -> None:
    """A VLMAgent that falls back internally is excluded from the vote + counted.

    VLMAgent.decide swallows backend/parse errors and returns a fallback action
    (consecutive_fallbacks increments) instead of raising.  The MOA must treat
    that as a failure: the fallback must NOT be counted as a `noop` vote, and
    backend_errors must increment so callers can apply back-off.
    """
    # Healthy agent votes click.
    healthy = _agent(json.dumps({"action": "click", "params": {"button": "left"}}))

    # A sub-agent whose backend always errors -> it falls back internally.
    broken_backend = MagicMock(spec=VLMBackend)
    broken_backend.complete.side_effect = RuntimeError("boom")
    broken = VLMAgent(
        backend=broken_backend,
        allowed_actions=["key_press", "mouse_move", "click", "noop"],
    )

    moa = MOAAgent([healthy, broken], weights=[1.0, 0.6])
    frame = _frame()
    winner = moa.decide("sig", [], frame, [])

    # The broken agent's internal fallback must NOT dilute the vote to noop.
    assert winner.action == "click"
    # One real failure is recorded (not swallowed as a noop vote).
    assert moa.backend_errors == 1
    # A valid vote was produced, so the decision is considered successful even
    # though one sub-agent fell back.
    assert moa.last_decision_succeeded is True


def test_moa_last_decision_succeeded_false_only_on_all_fail() -> None:
    """last_decision_succeeded is False only when every sub-agent fails."""
    broken_backend = MagicMock(spec=VLMBackend)
    broken_backend.complete.side_effect = RuntimeError("boom")
    a0 = VLMAgent(backend=broken_backend, allowed_actions=["noop"])
    a1 = VLMAgent(backend=broken_backend, allowed_actions=["noop"])

    moa = MOAAgent([a0, a1], weights=[1.0, 0.6])
    frame = _frame()
    # All fail -> fallback to first agent (also errors) -> noop, and flag False.
    winner = moa.decide("sig", [], frame, [])
    assert winner.action == "noop"
    assert moa.last_decision_succeeded is False


def test_normalize_action_unknown_becomes_noop() -> None:
    assert normalize_action(Action("frobnicate", {})).action == "noop"


def test_normalize_action_disallowed_key_becomes_noop() -> None:
    bad = normalize_action(Action("key_press", {"key": "supersecret"}))
    assert bad.action == "noop"


def test_normalize_action_valid_key_kept() -> None:
    good = normalize_action(Action("key_press", {"key": "W"}))
    assert good.action == "key_press"
    assert good.params == {"key": "w"}
