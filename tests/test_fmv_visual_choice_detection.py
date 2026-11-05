from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from qa_framework.gameplay_agent.actions import Action, ActionExecutor
from qa_framework.gameplay_agent.reward import FrameDiffReward
from qa_framework.gameplay_agent.skill_cache import SkillCache
from qa_framework.gameplay_agent.state_oracle import ProfileStateOracle
from qa_framework.gameplay_agent.vlm_agent import VLMAgent
from scripts.live_gameplay_agent import LiveGameplayAgent, _phrase_boxes, _scenario_choice_hints


class _ChoiceBackend:
    def __init__(self, response: str) -> None:
        self.response = response
        self.call: dict | None = None

    def complete(self, prompt: str, image: np.ndarray) -> str:
        raise AssertionError("choice fallback must use strict structured output")

    def complete_json(self, prompt: str, image: np.ndarray, *, schema_name: str, schema: dict) -> str:
        self.call = {"prompt": prompt, "schema_name": schema_name, "schema": schema}
        return self.response


def test_visual_choice_detector_accepts_only_grounded_source_label_and_valid_box() -> None:
    backend = _ChoiceBackend(json.dumps({"choices": [{
        "label": "GO LEFT", "x": 340, "y": 390, "w": 220, "h": 60, "confidence": 95,
    }]}))
    agent = VLMAgent(backend, ["click", "noop"])
    words = agent.detect_visible_story_choices(
        np.zeros((720, 1280, 3), dtype=np.uint8), ["Go Left"]
    )

    assert words == [{
        "text": "Go Left", "x": 340, "y": 390, "w": 220, "h": 60,
        "source": "vlm_visual_choice", "confidence": 95,
    }]
    assert backend.call["schema_name"] == "visible_story_choices"
    assert backend.call["schema"]["properties"]["choices"]["items"]["properties"]["label"]["enum"] == ["Go Left"]


def test_visual_choice_detector_rejects_unknown_low_confidence_and_out_of_bounds() -> None:
    response = {"choices": [
        {"label": "Kill Aya", "x": 20, "y": 20, "w": 80, "h": 30, "confidence": 99},
        {"label": "Go Left", "x": 20, "y": 20, "w": 80, "h": 30, "confidence": 60},
        {"label": "Go Left", "x": 1240, "y": 20, "w": 80, "h": 30, "confidence": 99},
    ]}
    agent = VLMAgent(_ChoiceBackend(json.dumps(response)), ["click", "noop"])

    assert agent.detect_visible_story_choices(
        np.zeros((720, 1280, 3), dtype=np.uint8), ["Go Left"]
    ) == []


def test_visual_choice_detector_rejects_duplicate_label_as_ambiguous() -> None:
    response = {"choices": [
        {"label": "Go Left", "x": 20, "y": 20, "w": 80, "h": 30, "confidence": 95},
        {"label": "Go Left", "x": 400, "y": 20, "w": 80, "h": 30, "confidence": 95},
    ]}
    agent = VLMAgent(_ChoiceBackend(json.dumps(response)), ["click", "noop"])

    assert agent.detect_visible_story_choices(
        np.zeros((720, 1280, 3), dtype=np.uint8), ["Go Left"]
    ) == []


def test_scenario_choice_hints_include_only_explicit_case_choices() -> None:
    assert _scenario_choice_hints({"case_id": "HBS-0002", "choice": "Go Left"}) == ("Go Left",)
    assert _scenario_choice_hints({"steps": [{"expected_choice": "Go Right"}]}) == ("Go Right",)
    assert _scenario_choice_hints({"case_id": "HBS-0001"}) == ()


def test_choice_candidates_expand_only_to_linked_siblings() -> None:
    oracle = ProfileStateOracle(
        [
            {"text": "Go Left", "scene_id": "left", "kind": "story_choice"},
            {"text": "Go Right", "scene_id": "right", "kind": "story_choice"},
            {"text": "Red Door", "scene_id": "other", "kind": "story_choice"},
        ],
        "highschoolblood-demo",
        [["Go Left", "Go Right"]],
    )

    assert oracle.visual_choice_candidates(("Go Left",)) == ("Go Left", "Go Right")
    assert oracle.visual_choice_candidates(("Red Door",)) == ("Red Door",)


class _FakeAgent:
    consecutive_fallbacks = 0

    def __init__(self) -> None:
        self.detect_calls = 0
        self.context = ""

    def detect_visible_story_choices(self, frame: np.ndarray, candidates: tuple[str, ...]) -> list[dict]:
        self.detect_calls += 1
        assert candidates == ("Go Left",)
        return [{"text": "Go Left", "x": 300, "y": 400, "w": 240, "h": 60,
                 "source": "vlm_visual_choice", "confidence": 95}]

    def observe(self, frame: np.ndarray) -> np.ndarray:
        return frame

    def decide(self, *, observation, context, state_sig, strategy, menu_keywords) -> Action:
        self.context = context
        return Action("noop", {})

    def learn(self, reward: float, done: bool) -> None:
        pass


def test_visual_choice_evidence_promotes_unknown_screen_and_is_traced(tmp_path: Path) -> None:
    agent = _FakeAgent()
    oracle = ProfileStateOracle(
        [{"text": "Go Left", "scene_id": "01_Prescene_S001_A", "kind": "story_choice"}],
        "highschoolblood-demo",
    )
    live = LiveGameplayAgent(
        agent=agent, cache=SkillCache(path=tmp_path / "cache.json"),
        executor=ActionExecutor(keyboard=object(), mouse=object()),
        reward_fn=FrameDiffReward(), window_rect=(0, 0, 1280, 720),
        menu_keywords=frozenset(), win_w=1280, win_h=720,
        trace_path=tmp_path / "trace.jsonl", strategy="fmv_passive",
        state_oracle=oracle, visual_choice_hints=("Go Left",),
    )
    frame = np.random.default_rng(17).integers(30, 220, (720, 1280, 3), dtype=np.uint8)
    next_frame = frame.copy()
    next_frame[100:120, 100:120] = 255

    live.step(frame, [], next_frame, decision_frame=np.zeros((360, 640, 3), dtype=np.uint8))

    trace = json.loads((tmp_path / "trace.jsonl").read_text(encoding="utf-8"))
    assert agent.detect_calls == 1
    assert "Go Left" in agent.context
    assert trace["action"] == "noop"
    assert trace["state_recognition"]["known"] is True
    assert trace["state_recognition"]["evidence_source"] == "vlm_visual_choice"
    assert trace["state_recognition"]["visual_choice_labels"] == ["Go Left"]
    assert '"Go Left" at (150,200)' in agent.context


def test_scenario_grounding_blocks_a_different_visible_sibling_choice(tmp_path: Path) -> None:
    class Executor:
        def __init__(self) -> None:
            self.actions: list[Action] = []

        def dispatch(self, action: Action) -> None:
            self.actions.append(action)

    executor = Executor()
    live = LiveGameplayAgent(
        agent=_FakeAgent(), cache=SkillCache(path=tmp_path / "cache.json"),
        executor=executor, reward_fn=FrameDiffReward(), window_rect=(0, 0, 1280, 720),
        menu_keywords=frozenset(), win_w=1280, win_h=720,
        trace_path=tmp_path / "trace.jsonl", strategy="fmv_passive",
        state_oracle=ProfileStateOracle([], "highschoolblood-demo"),
        visual_choice_hints=("Go Left",),
    )
    live._frame_size = (1280, 720)
    live._last_state_recognition = {
        "known": True,
        "evidence_source": "vlm_visual_choice",
        "matches": [
            {"text": "go left", "kind": "story_choice"},
            {"text": "go right", "kind": "story_choice"},
        ],
    }
    right_words = [
        {"text": "Go Left", "x": 250, "y": 380, "w": 200, "h": 50},
        {"text": "Go Right", "x": 650, "y": 380, "w": 220, "h": 50},
    ]

    executed = live._dispatch_action(Action("click", {"x": 750, "y": 400}), right_words)

    assert executed.action == "noop"
    assert executor.actions == [Action("noop", {})]


def test_scenario_grounding_blocks_ocr_sibling_and_subtitle_word(tmp_path: Path) -> None:
    class Executor:
        def __init__(self) -> None:
            self.actions: list[Action] = []

        def dispatch(self, action: Action) -> None:
            self.actions.append(action)

    executor = Executor()
    live = LiveGameplayAgent(
        agent=_FakeAgent(), cache=SkillCache(path=tmp_path / "cache.json"),
        executor=executor, reward_fn=FrameDiffReward(), window_rect=(0, 0, 1280, 720),
        menu_keywords=frozenset(), win_w=1280, win_h=720,
        trace_path=tmp_path / "trace.jsonl", strategy="fmv_passive",
        state_oracle=ProfileStateOracle([], "highschoolblood-demo"),
        visual_choice_hints=("Go Left",),
    )
    live._frame_size = (1280, 720)
    live._last_state_recognition = {
        "known": True,
        "matches": [{"text": "right", "kind": "story_choice"}],
    }
    subtitle_word = [{"text": "right?", "x": 250, "y": 380, "w": 200, "h": 50}]

    executed = live._dispatch_action(Action("click", {"x": 350, "y": 400}), subtitle_word)

    assert executed.action == "noop"
    assert executor.actions == [Action("noop", {})]


def test_scenario_click_snaps_to_requested_choice_box_center(tmp_path: Path) -> None:
    class Executor:
        def __init__(self) -> None:
            self.actions: list[Action] = []

        def dispatch(self, action: Action) -> None:
            self.actions.append(action)

    executor = Executor()
    live = LiveGameplayAgent(
        agent=_FakeAgent(), cache=SkillCache(path=tmp_path / "cache.json"),
        executor=executor, reward_fn=FrameDiffReward(), window_rect=(0, 0, 1280, 720),
        menu_keywords=frozenset(), win_w=1280, win_h=720,
        trace_path=tmp_path / "trace.jsonl", strategy="fmv_passive",
        state_oracle=ProfileStateOracle([], "highschoolblood-demo"),
        visual_choice_hints=("Take the Pill",),
    )
    live._frame_size = (640, 480)
    live._last_state_recognition = {
        "known": True,
        "matches": [{"text": "take the pill", "kind": "story_choice"}],
    }
    words = [
        {"text": "Take", "x": 200, "y": 380, "w": 38, "h": 20},
        {"text": "the", "x": 241, "y": 380, "w": 24, "h": 20},
        {"text": "Pill", "x": 270, "y": 380, "w": 42, "h": 20},
    ]

    executed = live._dispatch_action(Action("click", {"x": 256, "y": 417}), words)

    assert executed.params == {"button": "left", "x": 256, "y": 390}
    assert executor.actions[-1] == executed


def test_phrase_box_rejects_a_choice_suffix_inside_another_choice() -> None:
    words = [
        {"text": "Don't", "x": 100, "y": 20, "w": 40, "h": 20},
        {"text": "Try", "x": 145, "y": 20, "w": 30, "h": 20},
        {"text": "It", "x": 180, "y": 20, "w": 16, "h": 20},
    ]
    assert _phrase_boxes(["Try It"], words) == []
    assert _phrase_boxes(["Don't Try It"], words)
