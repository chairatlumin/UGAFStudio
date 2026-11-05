from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np

from qa_framework.gameplay_agent.actions import Action
from qa_framework.gameplay_agent.reward import FrameDiffReward
from qa_framework.gameplay_agent.skill_cache import SkillCache
from qa_framework.gameplay_agent.state_oracle import ProfileStateOracle
from qa_framework.gameplay_agent.vlm_agent import VLMAgent
from scripts.live_gameplay_agent import LiveGameplayAgent, normalize_params


class _MockBackend:
    """Returns a fixed VLM action for every completion call."""

    def __init__(self, action: dict) -> None:
        self._action = action

    def complete(self, prompt: str, image: np.ndarray) -> str:
        return json.dumps(self._action)


class _MockExecutor:
    """Records every dispatched action for inspection in tests."""

    def __init__(self) -> None:
        self.dispatched: list[Action] = []

    def dispatch(self, action: Action) -> None:
        self.dispatched.append(action)


def test_live_input_normalization_rejects_incomplete_and_out_of_bounds_actions() -> None:
    assert normalize_params(Action("key_press", {})).action == "noop"
    assert normalize_params(Action("mouse_move", {"x": 1})).action == "noop"
    assert normalize_params(Action("mouse_move", {"x": 80, "y": 2}), (16, 16)).action == "noop"
    assert normalize_params(Action("click", {"button": "left", "x": 2}), (16, 16)).action == "noop"


def test_stale_frame_is_traced_and_sends_no_input(tmp_path: Path) -> None:
    agent, executor, _ = _build_agent(
        backend_action={"action": "key_press", "params": {"key": "w"}},
        alt_action={"action": "key_press", "params": {"key": "space"}},
        alt_sig="other|" + "b" * 32,
        tmp_path=tmp_path,
    )
    frame = np.full((16, 16, 3), 128, dtype=np.uint8)
    agent.step(frame, [], frame, frame_captured_at=time.monotonic() - 10)
    assert executor.dispatched == []
    trace = json.loads((tmp_path / "trace.jsonl").read_text(encoding="utf-8").splitlines()[-1])
    assert trace["action"] == "skip"
    assert trace["sig"] == "stale-frame"


def test_fmv_unknown_screen_skips_decision_and_input(tmp_path: Path) -> None:
    agent, executor, _ = _build_agent(
        backend_action={"action": "key_press", "params": {"key": "w"}},
        alt_action={"action": "key_press", "params": {"key": "space"}},
        alt_sig="other|" + "b" * 32,
        tmp_path=tmp_path,
        strategy="fmv_passive",
        state_oracle=ProfileStateOracle([], "highschoolblood-demo"),
    )
    frame = np.full((16, 16, 3), 128, dtype=np.uint8)
    agent.step(frame, [{"text": "unrecognized screen"}], frame)
    assert executor.dispatched == []
    trace = json.loads((tmp_path / "trace.jsonl").read_text(encoding="utf-8").splitlines()[-1])
    assert trace["action"] == "skip"
    assert trace["params"]["reason"] == "unknown screen; FMV input skipped"
    assert trace["state_recognition"]["known"] is False


def test_fmv_known_choice_screen_can_reach_decision_agent(tmp_path: Path) -> None:
    oracle = ProfileStateOracle(
        [{"text": "Go Left", "scene_id": "01_Prescene_S001_A", "kind": "story_choice"}],
        "highschoolblood-demo",
    )
    agent, executor, _ = _build_agent(
        backend_action={"action": "click", "params": {"button": "left", "x": 4, "y": 4}},
        alt_action={"action": "key_press", "params": {"key": "space"}},
        alt_sig="other|" + "b" * 32,
        tmp_path=tmp_path,
        strategy="fmv_passive",
        state_oracle=oracle,
    )
    frame = np.full((16, 16, 3), 128, dtype=np.uint8)
    agent.step(frame, [{"text": "Go Left", "x": 2, "y": 2}], frame)
    assert executor.dispatched
    trace = json.loads((tmp_path / "trace.jsonl").read_text(encoding="utf-8").splitlines()[-1])
    assert trace["state_recognition"]["known"] is True
    assert trace["state_recognition"]["scene_ids"] == ["01_Prescene_S001_A"]


def _build_agent(
    *,
    backend_action: dict,
    alt_action: dict,
    alt_sig: str,
    tmp_path: Path,
    strategy: str = "menu_nav",
    state_oracle: ProfileStateOracle | None = None,
) -> tuple[LiveGameplayAgent, _MockExecutor, SkillCache]:
    """Construct a LiveGameplayAgent-like harness with mocked collaborators."""
    cache = SkillCache(path=tmp_path / "skills.json")
    # Seed the cache with a *known good* alternative for the same OCR part.
    cache.put(alt_sig, alt_action)
    cache.record_outcome(alt_sig, success=True)
    cache.record_outcome(alt_sig, success=True)

    backend = _MockBackend(backend_action)
    # Use a SEPARATE empty cache for the VLMAgent so the fuzzy/prefix match
    # does not hijack the decision with the alternative we seeded above.
    vlm = VLMAgent(
        backend=backend,
        allowed_actions=["key_press", "mouse_move", "click", "type_text", "noop"],
        cache=SkillCache.__new__(SkillCache),
    )
    vlm._cache._data = {}  # type: ignore[attr-defined]
    vlm._cache._path = tmp_path / "agent-cache.json"  # type: ignore[attr-defined]
    vlm._cache._outcomes = {}  # type: ignore[attr-defined]

    executor = _MockExecutor()
    window_rect = (0, 0, 100, 100)
    trace_path = tmp_path / "trace.jsonl"
    agent = LiveGameplayAgent(
        agent=vlm,
        cache=cache,
        executor=executor,
        reward_fn=FrameDiffReward(),
        window_rect=window_rect,
        menu_keywords=frozenset(),
        win_w=100,
        win_h=100,
        trace_path=trace_path,
        # Capture-health guard is disabled here: these tests use black synthetic
        # frames to drive stuck-detection; they are not about capture validity.
        capture_warn_threshold=0.0,
        strategy=strategy,
        state_oracle=state_oracle,
    )
    return agent, executor, cache


def test_ranked_alternative_dispatched_after_two_zero_rewards(tmp_path: Path) -> None:
    """After 2 zero rewards on the same OCR part, the top cached alternative
    (which differs from the executed action) is auto-dispatched."""
    # The VLM keeps deciding the same 'w' press; the cache holds a known-good
    # alternative 'space' for the identical OCR part "menu".
    backend_action = {"action": "key_press", "params": {"key": "w"}}
    alt_action = {"action": "key_press", "params": {"key": "space"}}
    alt_sig = "menu|" + "a" * 32

    agent, executor, _ = _build_agent(
        backend_action=backend_action,
        alt_action=alt_action,
        alt_sig=alt_sig,
        tmp_path=tmp_path,
    )

    ocr_words = [{"text": "menu", "x": 10, "y": 20, "w": 30, "h": 10}]
    frame = np.zeros((16, 16, 3), dtype=np.uint8)

    # Run three stuck steps (identical frames => reward always 0.0).
    for _ in range(3):
        agent.step(frame, ocr_words, frame)

    executed_keys = [a.params.get("key") for a in executor.dispatched if a.action == "key_press"]

    # The VLM decision ('w') must be dispatched every step.
    assert executed_keys.count("w") == 3

    # The ranked alternative ('space') must be dispatched exactly once, on the
    # second stuck step (zero_streak >= 2), and not again afterwards.
    assert executed_keys.count("space") == 1


def test_no_alternative_when_cache_empty_falls_back_to_escape(tmp_path: Path) -> None:
    """With no usable ranked alternative, the stuck-escape fallback fires."""
    backend_action = {"action": "key_press", "params": {"key": "w"}}
    # No alternative seeded for this OCR part; the agent should fall back to
    # injecting 'escape' once 3 consecutive zero rewards accumulate.
    agent, executor, _ = _build_agent(
        backend_action=backend_action,
        alt_action={"action": "key_press", "params": {"key": "space"}},
        alt_sig="other|" + "b" * 32,  # different OCR part -> not a match
        tmp_path=tmp_path,
    )

    ocr_words = [{"text": "menu", "x": 10, "y": 20, "w": 30, "h": 10}]
    frame = np.zeros((16, 16, 3), dtype=np.uint8)
    for _ in range(3):
        agent.step(frame, ocr_words, frame)

    escape_presses = [
        a
        for a in executor.dispatched
        if a.action == "key_press" and a.params.get("key") == "escape"
    ]
    assert len(escape_presses) == 1
