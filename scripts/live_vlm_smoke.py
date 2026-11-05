from __future__ import annotations

import argparse
from unittest.mock import Mock

import cv2
import numpy as np
from loguru import logger

from qa_framework.gameplay_agent.actions import Action, ActionExecutor
from qa_framework.gameplay_agent.backends import OpenAICompatBackend
from qa_framework.gameplay_agent.vlm_agent import VLMAgent


def make_synthetic_frame() -> np.ndarray:
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    frame[:] = (100, 150, 200)
    cv2.putText(
        frame,
        "MENU",
        (270, 240),
        cv2.FONT_HERSHEY_SIMPLEX,
        1.5,
        (255, 255, 255),
        3,
    )
    return frame


def main() -> int:
    parser = argparse.ArgumentParser(description="VLM Live Smoke Test")
    parser.add_argument(
        "--iterations",
        type=int,
        default=3,
        help="Number of decide iterations (appends history each loop)",
    )
    args = parser.parse_args()

    # Build backend
    backend = OpenAICompatBackend(
        base_url="http://localhost:1234/v1",
        model="google/gemma-4-e2b",
        api_key="lm-studio",
    )

    # Build agent
    agent = VLMAgent(
        backend=backend,
        allowed_actions=["key_press", "click", "mouse_move", "noop"],
    )

    # Mock default services so ActionExecutor dispatch uses Mocks, not real input
    ActionExecutor._default_kb = Mock()
    ActionExecutor._default_ms = Mock()

    # Generate synthetic frame (do NOT capture a real game)
    frame = make_synthetic_frame()

    for i in range(args.iterations):
        logger.info("Iteration {} / {}", i + 1, args.iterations)

        # Observe
        observe_result = agent.observe(frame)

        # Decide
        action: Action = agent.decide(observe_result)

        action_name = action.action
        action_params = action.params

        print(f"Iteration {i + 1}: raw response from backend sent via HTTP")
        print(f"Parsed action: {action_name}")
        print(f"Action params: {action_params}")

        # Dispatch through ActionExecutor with Mock keyboard/mouse
        executor = ActionExecutor(keyboard=Mock(), mouse=Mock())
        executor.dispatch(action)
        print("  -> Dispatch completed via Mock executor")

        # Check if the decided action is in the allowed set
        if action_name in ["key_press", "click", "mouse_move", "noop"]:
            print(f"  -> PASS: action '{action_name}' is allowed")
        else:
            print(f"  -> FAIL: action '{action_name}' is NOT in allowed actions")
            return 1

    print("PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
