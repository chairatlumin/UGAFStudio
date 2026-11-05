"""Benchmark decision latency per VLM backend.

Smoke-test the A2A pipeline with a given engineer model (default
``google/gemma-4-e2b``) and measure the per-call decision latency of
:class:`VLMAgent` over an :class:`OpenAICompatBackend`.

No real input is dispatched (a :class:`MockExecutor` is used) and no frames
are looped — a single frame is captured from the Agent Veil window and reused
for every ``decide()`` call so that timing reflects backend + parse cost only.

Usage:
    PYTHONPATH=. python scripts/bench_brain.py --steps 2
    PYTHONPATH=. python scripts/bench_brain.py --models gemma-4-e2b,llama-3.2
"""

from __future__ import annotations

import argparse
import statistics
import time
from typing import Any

import cv2
import numpy as np
from loguru import logger

from qa_framework.gameplay_agent.actions import Action
from qa_framework.gameplay_agent.backends import OpenAICompatBackend
from qa_framework.gameplay_agent.vlm_agent import (
    VLMAgent,
    _extract_json_response,
)
from scripts.live_gameplay_agent import (
    find_game_hwnd,
    get_window_rect,
    grab_frame,
)

WINDOW_TITLE = "Agent Veil"
ALLOWED_ACTIONS = ["key_press", "mouse_move", "click", "type_text", "noop"]
SYSTEM_PROMPT = (
    "You are a gameplay QA agent. Observe the frame and output exactly one "
    'action as JSON: {"action": "...", "params": {}}.'
)
BASE_URL = "http://localhost:1234/v1"
API_KEY = "lm-studio"
MAX_FRAME_DIM = 640


def _downscale_frame(frame: np.ndarray, max_dim: int = MAX_FRAME_DIM) -> np.ndarray:
    """Downscale *frame* so its longest side is at most *max_dim*."""
    h, w = frame.shape[:2]
    long_side = max(h, w)
    if long_side <= max_dim:
        return frame
    scale = max_dim / float(long_side)
    return cv2.resize(frame, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)


class MockExecutor:
    """No-op action executor — never dispatches real input."""

    def dispatch(self, action: Action) -> None:  # noqa: D401
        # Intentionally do nothing: this is a benchmark, not a playthrough.
        _ = action


class CountingBackend:
    """Wrap a VLM backend and count responses that fail JSON parsing.

    Backend exceptions are re-raised (so the caller can treat them as errors)
    but also tallied in ``errors`` so the summary reflects them.
    """

    def __init__(self, backend: OpenAICompatBackend) -> None:
        self._backend = backend
        self.parse_failures = 0
        self.errors = 0

    def complete(self, prompt: str, image: np.ndarray) -> str:
        try:
            raw = self._backend.complete(prompt, image)
        except Exception:
            self.errors += 1
            raise
        parsed = _extract_json_response(raw)
        if not (parsed and "action" in parsed and "params" in parsed):
            self.parse_failures += 1
        return raw


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Benchmark VLM decision latency per model.",
    )
    parser.add_argument(
        "--models",
        default="google/gemma-4-e2b",
        help="Comma-separated LM Studio model ids (default: %(default)s).",
    )
    parser.add_argument(
        "--steps",
        type=int,
        default=5,
        help="Number of decide() calls per model (default: %(default)s).",
    )
    parser.add_argument(
        "--base-url",
        default=BASE_URL,
        help="OpenAI-compatible base URL (default: %(default)s).",
    )
    return parser


def bench_model(
    model: str,
    frame: np.ndarray,
    steps: int,
    base_url: str,
) -> dict[str, Any] | None:
    """Run the benchmark for one *model*; return a summary dict or ``None`` (SKIP)."""
    try:
        backend = OpenAICompatBackend(
            base_url=base_url,
            api_key=API_KEY,
            model=model,
            max_tokens=512,
        )
    except ValueError as exc:
        logger.error("Model {!r} backend init failed: {}", model, exc)
        return None

    counting = CountingBackend(backend)
    agent = VLMAgent(
        backend=counting,
        allowed_actions=ALLOWED_ACTIONS,
        system_prompt=SYSTEM_PROMPT,
    )
    _executor = MockExecutor()  # no real input is ever dispatched

    # Warm-up / model-availability probe.  VLMAgent.decide() swallows backend
    # errors and returns a fallback action, so we probe the raw backend here:
    # if the model is not loaded the call raises and we SKIP this model.
    try:
        backend.complete("probe", frame)
    except Exception as exc:  # noqa: BLE001 - surface any backend error as SKIP
        logger.warning("Model {!r} not available, skipping: {}", model, exc)
        print(f"SKIP {model}: model not loaded ({exc})")
        return None

    latencies: list[float] = []
    errors = 0
    for i in range(steps):
        try:
            start = time.perf_counter()
            agent.decide(frame)
            latencies.append(time.perf_counter() - start)
        except Exception as exc:  # noqa: BLE001
            logger.error("decide() error on {!r} step {}: {}", model, i, exc)
            errors += 1

    if not latencies:
        print(f"SKIP {model}: all {steps} decide() calls failed")
        return None

    return {
        "model": model,
        "n": len(latencies),
        "mean": statistics.mean(latencies),
        "median": statistics.median(latencies),
        "max": max(latencies),
        "min": min(latencies),
        "parse_failures": counting.parse_failures,
        "errors": errors,
    }


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    models = [m.strip() for m in args.models.split(",") if m.strip()]
    if not models:
        logger.error("No models specified.")
        return 1

    # --- locate the game window (required) ---------------------------------
    wins = find_game_hwnd(WINDOW_TITLE)
    if not wins:
        msg = (
            f"Game window not found.  Make sure the '{WINDOW_TITLE}' window is "
            "running (the game must be open) before running this benchmark."
        )
        logger.error(msg)
        print(msg, flush=True)
        return 1

    hwnd, title = wins[0]
    left, top, right, bottom = get_window_rect(hwnd)
    logger.info("Found window {!r} rect=({},{},{},{})", title, left, top, right, bottom)

    # --- capture a single frame, reused for every decide() call ------------
    frame = grab_frame(hwnd)
    # Downscale to a sensible VLM input size so the latency benchmark stays
    # fast and predictable (the pipeline — capture, encode, decode, decide —
    # is still exercised end-to-end).
    frame = _downscale_frame(frame, max_dim=640)
    logger.info("Captured + downscaled frame shape={}", frame.shape)

    # --- benchmark each model ----------------------------------------------
    print("\n=== VLM Decision Latency Benchmark ===", flush=True)
    print(f"models: {', '.join(models)}", flush=True)
    print(f"steps per model: {args.steps}", flush=True)

    summaries: list[dict[str, Any]] = []
    for model in models:
        summary = bench_model(model, frame, args.steps, args.base_url)
        if summary is None:
            continue
        summaries.append(summary)
        print(
            f"\n[{model}]  n={summary['n']}  errors={summary['errors']}\n"
            f"  mean   : {summary['mean']:.4f}s\n"
            f"  median : {summary['median']:.4f}s\n"
            f"  min    : {summary['min']:.4f}s\n"
            f"  max    : {summary['max']:.4f}s\n"
            f"  parse_failures: {summary['parse_failures']}",
            flush=True,
        )

    print("\n=== Summary ===", flush=True)
    if not summaries:
        print("No models benchmarked successfully (all SKIPPED).", flush=True)
        return 0

    for s in summaries:
        print(
            f"{s['model']:<28} mean={s['mean']:.4f}s  "
            f"median={s['median']:.4f}s  max={s['max']:.4f}s  "
            f"parse_fail={s['parse_failures']}",
            flush=True,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
