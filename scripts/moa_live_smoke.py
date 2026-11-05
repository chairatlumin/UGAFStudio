"""Standalone MOA v2 live smoke test against real LM Studio VLM endpoints.

Builds 3 local VLM backends (qwen2.5-vl-7b, gemma-4-e2b, qwen3.8-27b) and
runs a single MOAAgent decision over a synthetic frame, exercising:

* real multi-VLM parallel voting (majority),
* the early-exit low-latency path (returns after the fast primary, drains
  slow stragglers in the background),
* reward-weighted voting feedback (update_rewards).

No game window required. Validates that moa.py v2 talks to the live models.
"""

from __future__ import annotations

import argparse
import time

import numpy as np

from qa_framework.gameplay_agent.backends import OpenAICompatBackend
from qa_framework.gameplay_agent.moa import MOAAgent, _action_signature, normalize_action
from qa_framework.gameplay_agent.vlm_agent import VLMAgent

ALLOWED_ACTIONS = ["key_press", "mouse_move", "click", "type_text", "noop"]

MOA_SPECS = [
    ("qwen/qwen2.5-vl-7b", 1.0),
    ("google/gemma-4-e2b", 0.6),
    ("qwen/qwen3.8-27b", 0.4),
]


def _synthetic_frame(text: str = "MENU: Start  /  Settings  /  Exit") -> np.ndarray:
    """A simple BGR frame with white text on a dark background for the VLM."""
    import cv2

    img = np.full((480, 640, 3), 32, dtype=np.uint8)
    cv2.putText(
        img,
        text,
        (40, 240),
        cv2.FONT_HERSHEY_SIMPLEX,
        1.0,
        (235, 235, 235),
        2,
        cv2.LINE_AA,
    )
    return img


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="MOA v2 live smoke test.")
    parser.add_argument("--base-url", default="http://localhost:1234/v1")
    parser.add_argument("--timeout", type=float, default=90.0)
    parser.add_argument("--early-exit", action="store_true", default=True)
    parser.add_argument("--no-early-exit", dest="early_exit", action="store_false")
    args = parser.parse_args(argv)

    backends = {}
    sub_agents: list[VLMAgent] = []
    for model, weight in MOA_SPECS:
        b = OpenAICompatBackend(
            base_url=args.base_url,
            model=model,
            api_key="lm-studio",
            max_tokens=512,
            timeout=args.timeout,
        )
        backends[model] = b
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

    moa = MOAAgent(
        sub_agents,
        weights=[w for _, w in MOA_SPECS],
        early_exit=args.early_exit,
        min_votes=1,
    )

    frame = _synthetic_frame()
    print(f"MOA early_exit={args.early_exit}, sub_agents={len(sub_agents)}")
    print("Querying live VLMs (this calls LM Studio)...")

    t0 = time.perf_counter()
    winner = moa.decide(observation=frame, state_sig="smoke-1")
    elapsed = time.perf_counter() - t0

    print(f"  decision elapsed: {elapsed:.2f}s")
    print(f"  winner action : {winner.action}  params={winner.params}")
    print(f"  vote counts   : {moa._last_counts}")
    print(f"  backend_errors: {moa.backend_errors}")

    # Reward-weighted feedback: tell MOA the winner changed the screen.
    moa.update_rewards({_action_signature(normalize_action(winner)): 1.0})
    winner2 = moa.decide(observation=frame, state_sig="smoke-2")
    print(f"  after reward  : {winner2.action}  (counts={moa._last_counts})")

    # Basic sanity: we must get a normalized, dispatchable action.
    assert normalize_action(winner).action in ALLOWED_ACTIONS, winner
    print("SMOKE RESULT: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
