from __future__ import annotations

import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np

from qa_framework.playbook import Playbook, TraceEvent

# ---------------------------------------------------------------------------
# Frame hash computation
# ---------------------------------------------------------------------------


def compute_frame_hash(frame: np.ndarray) -> str:
    """Compute 256-bit perceptual hash from a frame.

    Steps:
    1. Resize to 16×16 grayscale
    2. 2-bit quantise (reduce to 4 levels)
    3. Compare each pixel to the mean → 256-bit hash string (64 hex chars)
    Compare via Hamming distance (threshold < 10 = same state).
    """
    if frame.ndim == 3:
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    else:
        gray = frame
    small = cv2.resize(gray, (16, 16), interpolation=cv2.INTER_AREA)
    # 2-bit quantize: keep top 2 bits (floor divide by 64)
    quantized = (small // 64).astype(np.uint8)  # values 0..3
    mean_val = float(quantized.mean())
    bits = (quantized >= mean_val).astype(np.uint8)  # 256 bits
    bit_str = "".join(str(b) for b in bits.flatten())
    num = int(bit_str, 2)
    hex_str = format(num, "064x")
    return hex_str


# ---------------------------------------------------------------------------
# State signature (OCR-based label detection)
# ---------------------------------------------------------------------------


def compute_state_signature(frame: np.ndarray) -> str:
    """Detect a simple state label from a frame using OCR.

    Reuses app.vision.OCREngine when available; otherwise returns a stub
    label based on frame aspect-ratio / dominant colour heuristics.
    """
    try:
        from app.vision.ocr import OCREngine

        engine = OCREngine()
        if not engine.available():
            return _stub_state_signature(frame)
        # Capture the full window for OCR
        txt = engine.read(
            frame,
            scale=3,
            psm=7,
            config="--oem 3 -c tessedit_char_whitelist=0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ",
        )
        txt = txt.strip().lower()
        if txt:
            # Map common UI labels
            mapping = {
                "menu": "menu",
                "health": "combat",
                "mana": "combat",
                "inventory": "inventory",
                "pause": "menu",
                "loading": "loading",
                "gameplay": "gameplay",
                "combat": "combat",
                "battle": "combat",
            }
            for key, label in mapping.items():
                if key in txt:
                    return label
            return txt[:20]  # fallback: first 20 chars
    except Exception:
        pass
    return _stub_state_signature(frame)


def _stub_state_signature(frame: np.ndarray) -> str:
    """Fallback state label when OCR is unavailable."""
    h, w = frame.shape[:2]
    if w > h:
        return "landscape"
    if w < h:
        return "portrait"
    return "squared"


# ---------------------------------------------------------------------------
# TraceRecorder
# ---------------------------------------------------------------------------


class TraceRecorder:
    """Wraps action executor, logs each (action, frame_hash, state_signature).

    Each recorded step is appended to an async-JSONL file so I/O does not
    block the gameplay loop.
    """

    def __init__(
        self,
        game_id: int,
        output_path: Path | None = None,
    ) -> None:
        self.game_id = game_id
        if output_path is None:
            ts = int(datetime.now().timestamp())
            output_path = Path(".ai") / "traces" / f"{game_id}_{ts}.jsonl"
        self.output_path = Path(output_path)
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._events: list[TraceEvent] = []
        self._executor = ThreadPoolExecutor(max_workers=1)
        self._running = False

    def _write_event(self, event: TraceEvent) -> None:
        """Append one JSONL line to the trace file."""
        data = {
            "timestamp": event.timestamp,
            "action": event.action,
            "frame_hash": event.frame_hash,
            "state_signature": event.state_signature,
        }
        line = json.dumps(data, ensure_ascii=False)
        with self._lock:
            with self.output_path.open("a", encoding="utf-8") as f:
                f.write(line + "\n")

    def record_action(self, action_name: str, frame: np.ndarray) -> TraceEvent:
        """Capture one step: compute hash + state signature, log it.

        Returns the TraceEvent that was recorded.
        """
        frame_hash = compute_frame_hash(frame)
        state_sig = compute_state_signature(frame)
        event = TraceEvent(
            timestamp=time.time(),
            action=action_name if action_name else None,
            frame_hash=frame_hash,
            state_signature=state_sig,
        )
        self._events.append(event)
        # Async write – fire-and-forget
        self._executor.submit(self._write_event, event)
        return event

    def finalize(self, success: bool) -> Playbook:
        """Finalize recording and return a Playbook instance.

        :param success: True if the QA run passed, False if it failed.
        :return: Playbook containing all recorded events.
        """
        self._running = False
        # Build Playbook from collected events
        playbook = Playbook(
            game_id=self.game_id,
            goal=getattr(self, "_goal", "unknown"),
            events=self._events,
            success_count=1 if success else 0,
            fail_count=0 if success else 1,
            last_run=time.time(),
        )
        # Final flush of any pending writes
        self._executor.shutdown(wait=False)
        return playbook

    def set_goal(self, goal: str) -> None:
        """Set the QA goal for this recording session."""
        self._goal = goal
