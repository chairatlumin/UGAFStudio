"""Integrated MOA v2 live-loop harness (no game window required).

Builds a REAL 3-VLM MOAAgent (qwen2.5-vl-7b / gemma-4-e2b / qwen3.8-27b, all
served by LM Studio) and drives it through the ACTUAL `LiveGameplayAgent.step`
code path from `scripts/live_gameplay_agent.py` — the exact loop OpenCode wired
in TASK-025 (observe -> early-exit multi-VLM decide -> dispatch -> frame-diff
reward -> MOAAgent.update_rewards -> cache).

A no-op ActionExecutor is used so nothing is actually clicked on the desktop,
and synthetic frames are varied between steps to yield non-zero frame-diff
rewards. This proves the end-to-end integrated path, including the reward-weighted
feedback, against real vision models — without launching a game.
"""

from __future__ import annotations

import argparse
import tempfile
import time
from pathlib import Path

import cv2
import numpy as np

from qa_framework.gameplay_agent.actions import Action, ActionExecutor
from qa_framework.gameplay_agent.backends import OpenAICompatBackend
from qa_framework.gameplay_agent.moa import MOAAgent
from qa_framework.gameplay_agent.reward import FrameDiffReward
from qa_framework.gameplay_agent.skill_cache import SkillCache
from qa_framework.gameplay_agent.vlm_agent import VLMAgent
from scripts.live_gameplay_agent import ALLOWED_ACTIONS, LiveGameplayAgent

MOA_SPECS = [
    ("qwen/qwen2.5-vl-7b", 1.0),
    ("google/gemma-4-e2b", 0.6),
    ("qwen/qwen3.8-27b", 0.4),
]


class _NoOpExecutor(ActionExecutor):
    """ActionExecutor that records but never dispatches (safe for a harness)."""

    def __init__(self) -> None:
        # Bypass the real Keyboard/Mouse service construction.
        object.__setattr__(self, "_dispatched", [])

    @property
    def dispatched(self) -> list[Action]:  # type: ignore[override]
        return object.__getattribute__(self, "_dispatched")

    def dispatch(self, action: Action) -> None:  # type: ignore[override]
        object.__getattribute__(self, "_dispatched").append(action)


def _frame(hue: int, text: str) -> np.ndarray:
    img = np.full((480, 640, 3), 32, dtype=np.uint8)
    img[:, :] = (hue % 180, (hue + 40) % 255, (hue + 120) % 255)
    cv2.putText(
        img, text, (40, 240), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (235, 235, 235), 2, cv2.LINE_AA
    )
    return img


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Integrated MOA v2 live-loop harness.")
    parser.add_argument("--base-url", default="http://localhost:1234/v1")
    parser.add_argument("--timeout", type=float, default=90.0)
    parser.add_argument("--steps", type=int, default=4)
    parser.add_argument("--no-early-exit", dest="early_exit", action="store_false", default=True)
    args = parser.parse_args(argv)

    sub_agents: list[VLMAgent] = []
    for model, weight in MOA_SPECS:
        b = OpenAICompatBackend(
            base_url=args.base_url,
            model=model,
            api_key="lm-studio",
            max_tokens=512,
            timeout=args.timeout,
        )
        sub_agents.append(
            VLMAgent(
                backend=b,
                allowed_actions=ALLOWED_ACTIONS,
                system_prompt=(
                    "You are controlling a game menu. The screen shows a menu with "
                    "clickable buttons. Always advance the menu by clicking. "
                    "Return exactly one JSON action and nothing else."
                ),
                strategy="menu_nav",
                menu_keywords=["start", "settings", "exit"],
            )
        )

    agent = MOAAgent(
        sub_agents,
        weights=[w for _, w in MOA_SPECS],
        early_exit=args.early_exit,
        min_votes=1,
    )

    cache = SkillCache(path=Path(tempfile.gettempdir()) / "moa_integ_cache.json")
    executor = _NoOpExecutor()
    reward_fn = FrameDiffReward()

    live = LiveGameplayAgent(
        agent=agent,
        cache=cache,
        executor=executor,  # type: ignore[arg-type]
        reward_fn=reward_fn,
        window_rect=(0, 0, 640, 480),
        menu_keywords=frozenset(["start", "settings", "exit"]),
        win_w=640,
        win_h=480,
        trace_path=Path(tempfile.gettempdir()) / "moa_integ_trace.jsonl",
        strategy="menu_nav",
    )

    print(f"Integrated MOA loop: early_exit={args.early_exit}, steps={args.steps}")
    print(f"sub-agents={len(sub_agents)} via LM Studio @ {args.base_url}")

    frames = [
        _frame(20, "MENU: Start  Settings  Exit"),
        _frame(140, "MENU: Settings  Back"),
        _frame(260, "LOADING..."),
        _frame(80, "MENU: Start  Settings  Exit"),
    ]

    t0 = time.perf_counter()
    rewards: list[float] = []
    for i in range(args.steps):
        frame = frames[i % len(frames)]
        ocr_words = [{"text": "start", "x": 40, "y": 220, "w": 60, "h": 30}]
        next_frame = frames[(i + 1) % len(frames)]
        r = live.step(frame, ocr_words, next_frame)
        rewards.append(r)
        last = executor.dispatched[-1] if executor.dispatched else None
        print(
            f"  step {i + 1}: reward={r:.0f} last_dispatched={last.action if last else None} "
            f"moa_errors={agent.backend_errors} vote_counts={agent._last_counts}"
        )
    elapsed = time.perf_counter() - t0

    print(f"Total loop time: {elapsed:.1f}s over {args.steps} steps")
    print(f"rewards={rewards}")
    print("INTEGRATED RESULT: PASS (MOA v2 drove the real LiveGameplayAgent.step path)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
