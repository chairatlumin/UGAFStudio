from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from qa_framework.gameplay_agent.actions import Action
from qa_framework.gameplay_agent.reward import FrameDiffReward
from qa_framework.gameplay_agent.vlm_agent import VLMAgent
from scripts.live_gameplay_agent import LiveGameplayAgent

PROFILE_PATH = Path(__file__).resolve().parent.parent / "scripts" / "game_profiles.json"


# ---------------------------------------------------------------------------
# Profile file (TASK-024 part 1)
# ---------------------------------------------------------------------------


def test_profiles_include_legacy_games_and_highschool_blood_demo() -> None:
    """Legacy genres stay available alongside the requested FMV demo profile."""
    data = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
    assert {"agent-veil", "shinebringers", "unforgettable-love", "highschoolblood-demo"} <= set(data)
    assert data["agent-veil"]["game_type"] == "menu"
    assert data["shinebringers"]["game_type"] == "action"
    assert data["unforgettable-love"]["game_type"] == "visual_novel"
    assert data["highschoolblood-demo"]["game_type"] == "fmv_visual_novel"
    assert data["little-nightmares"]["game_type"] == "horror_platformer"
    assert data["little-nightmares"]["requires_manual_launch"] is True


def test_each_profile_has_strategy_dispatch_key() -> None:
    """Every profile carries a `strategy` key used for dispatch branching."""
    data = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
    for name, profile in data.items():
        assert "strategy" in profile, f"{name} missing 'strategy'"
        assert profile["strategy"] in {
            "menu_nav",
            "realtime_flick",
            "vn_advance",
            "fmv_passive",
            "platformer_stealth",
        }, f"{name} has unknown strategy {profile['strategy']!r}"


# ---------------------------------------------------------------------------
# Strategy branching (TASK-024 part 2) - unit tested via mocks
# ---------------------------------------------------------------------------


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


class _FakeCache:
    """SkillCache stand-in that counts record_outcome (reward pruning) calls."""

    def __init__(self) -> None:
        self.record_outcome_calls = 0

    def record_outcome(self, sig: str, success: bool) -> None:
        self.record_outcome_calls += 1

    def rank_by_ocr(self, ocr_part: str, top_k: int = 3) -> list[dict]:
        return []


def _fresh_vlm(backend_action: dict) -> VLMAgent:
    """A VLMAgent backed by a throwaway empty cache (no cache hits)."""
    backend = _MockBackend(backend_action)
    return VLMAgent(
        backend=backend,
        allowed_actions=["key_press", "mouse_move", "click", "type_text", "noop"],
        cache=None,
    )


def _make_agent(
    strategy: str,
    backend_action: dict,
    tmp_path: Path,
    menu_keywords: frozenset[str] | None = None,
) -> tuple[LiveGameplayAgent, _MockExecutor, _FakeCache]:
    cache = _FakeCache()
    executor = _MockExecutor()
    agent = LiveGameplayAgent(
        agent=_fresh_vlm(backend_action),
        cache=cache,  # type: ignore[arg-type]
        executor=executor,  # type: ignore[arg-type]
        reward_fn=FrameDiffReward(),
        window_rect=(0, 0, 100, 100),
        menu_keywords=menu_keywords or frozenset(),
        win_w=100,
        win_h=100,
        trace_path=tmp_path / "trace.jsonl",
        strategy=strategy,
    )
    return agent, executor, cache


def test_menu_nav_injects_escape_on_stuck(tmp_path: Path) -> None:
    """menu_nav keeps the legacy stuck-escape keyboard fallback."""
    agent, executor, _ = _make_agent(
        "menu_nav",
        {"action": "key_press", "params": {"key": "w"}},
        tmp_path=tmp_path,
    )
    ocr_words = [{"text": "menu", "x": 10, "y": 20, "w": 30, "h": 10}]
    frame = np.full((16, 16, 3), 128, dtype=np.uint8)
    for _ in range(3):
        agent.step(frame, ocr_words, frame)

    escapes = [
        a
        for a in executor.dispatched
        if a.action == "key_press" and a.params.get("key") == "escape"
    ]
    assert len(escapes) == 1


def test_realtime_flick_skips_escape_and_menu_matching(tmp_path: Path) -> None:
    """realtime_flick (action) games have no menus: no escape, no OCR matching."""
    agent, executor, _ = _make_agent(
        "realtime_flick",
        {"action": "key_press", "params": {"key": "w"}},
        tmp_path=tmp_path,
        menu_keywords=frozenset({"menu", "exit"}),
    )
    # Even though a "menu" keyword is present, realtime_flick disables matching.
    assert agent._menu_keywords == frozenset()

    ocr_words = [{"text": "menu", "x": 10, "y": 20, "w": 30, "h": 10}]
    frame = np.full((16, 16, 3), 128, dtype=np.uint8)
    for _ in range(3):
        agent.step(frame, ocr_words, frame)

    escapes = [
        a
        for a in executor.dispatched
        if a.action == "key_press" and a.params.get("key") == "escape"
    ]
    # Action games have no menus, so the stuck-escape must never fire.
    assert len(escapes) == 0


def test_vn_advance_advances_on_noop_and_skips_cache_pruning(tmp_path: Path) -> None:
    """vn_advance converts a no-op into a click, and skips reward cache pruning."""
    agent, executor, cache = _make_agent(
        "vn_advance",
        {"action": "noop", "params": {}},
        tmp_path=tmp_path,
    )
    ocr_words: list[dict] = []
    frame = np.full((16, 16, 3), 128, dtype=np.uint8)
    agent.step(frame, ocr_words, frame)

    clicks = [a for a in executor.dispatched if a.action == "click"]
    assert clicks, "vn_advance should advance dialogue with a click on noop"

    # reward-based cache pruning is skipped for linear VNs.
    assert cache.record_outcome_calls == 0


def test_vn_advance_clicks_choice_keyword_coords(tmp_path: Path) -> None:
    """vn_advance clicks the on-screen coords of an OCR `choice` keyword."""
    agent, executor, _ = _make_agent(
        "vn_advance",
        {"action": "click", "params": {"button": "left"}},
        tmp_path=tmp_path,
        menu_keywords=frozenset({"choice", "next", "skip"}),
    )
    # The 16px fixture is scaled to the 100px game window before dispatch.
    ocr_words = [{"text": "choice", "x": 2, "y": 3, "w": 4, "h": 2}]
    frame = np.full((16, 16, 3), 128, dtype=np.uint8)
    agent.step(frame, ocr_words, frame)

    clicks = [
        a
        for a in executor.dispatched
        if a.action == "click" and a.params.get("x") == 25 and a.params.get("y") == 25
    ]
    assert clicks, "vn_advance should click the 'choice' keyword's centre (25,25)"


def test_vlm_prompt_includes_strategy_and_keywords() -> None:
    """The VLM prompt carries the genre strategy + menu keywords context."""
    captured: list[str] = []

    class _CaptureBackend:
        def complete(self, prompt: str, image: np.ndarray) -> str:
            captured.append(prompt)
            return json.dumps({"action": "noop", "params": {}})

    vlm = VLMAgent(
        backend=_CaptureBackend(),
        allowed_actions=["noop"],
        strategy="vn_advance",
        menu_keywords=["next", "choice"],
    )
    vlm.decide(np.zeros((4, 4, 3), dtype=np.uint8))
    assert captured, "backend was never called"
    assert "vn_advance" in captured[0]
    assert "next" in captured[0] and "choice" in captured[0]
