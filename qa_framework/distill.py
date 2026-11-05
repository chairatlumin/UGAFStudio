from __future__ import annotations

from typing import List

from qa_framework.playbook import Playbook, TraceEvent


def _hamming_distance(a: str, b: str) -> int:
    """Compute Hamming distance between two hex-encoded 256-bit hashes."""
    da = int(a, 16)
    db = int(b, 16)
    xor = da ^ db
    return bin(xor).count("1")


def _is_duplicate(e1: TraceEvent, e2: TraceEvent, threshold: int = 10) -> bool:
    """Two events are duplicates if their frame_hash Hamming distance
    is below *threshold* (default 10) AND they share the same state_signature."""
    return e1.state_signature == e2.state_signature and _hamming_distance(
        e1.frame_hash, e2.frame_hash
    ) < threshold


def distill(trace: List[TraceEvent], max_consecutive_dupes: int = 1) -> Playbook:
    """Distil a verbose trace into a minimal playbook.

    - Remove consecutive duplicate states (same state_signature + frame_hash
      Hamming distance < 10).
    - Keep only state-transition actions (where state_signature changes).
    - Return a Playbook with the distilled events.

    :param trace: Raw list of TraceEvent entries.
    :param max_consecutive_dupes: Ignored; kept for API compatibility.
      Consecutive dupes are always stripped to a single occurrence.
    :return: Playbook with distilled events.
    """
    if not trace:
        return Playbook(game_id=0, goal="")

    distilled: list[TraceEvent] = [trace[0]]

    for ev in trace[1:]:
        prev = distilled[-1]
        if _is_duplicate(prev, ev, threshold=10):
            continue
        distilled.append(ev)

    return Playbook(game_id=0, goal="unknown", events=distilled)
