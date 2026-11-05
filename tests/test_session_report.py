"""Unit tests for scripts/session_report.build_report."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.session_report import build_report


def _write_trace(path: Path, entries: list[dict]) -> None:
    with path.open("w", encoding="utf-8") as fh:
        for e in entries:
            fh.write(json.dumps(e) + "\n")


def test_build_report_returns_expected_keys(tmp_path: Path) -> None:
    trace = tmp_path / "skill_trace.jsonl"
    out = tmp_path / "report.html"
    entries = [
        {
            "sig": "a",
            "action": "click",
            "params": {},
            "cached": False,
            "reward": 0.0,
            "latency": 0.1,
        },
        {
            "sig": "b",
            "action": "key_press",
            "params": {"key": "w"},
            "cached": True,
            "reward": 1.0,
            "latency": 0.2,
        },
        {
            "sig": "c",
            "action": "noop",
            "params": {},
            "cached": False,
            "reward": -0.5,
            "latency": 0.3,
        },
    ]
    _write_trace(trace, entries)

    stats = build_report(trace, out)

    assert set(stats) == {"steps", "cache_hits", "rewards_sum", "mean_latency"}
    assert stats["steps"] == 3
    assert stats["cache_hits"] == 1
    assert stats["rewards_sum"] == 0.5
    assert abs(stats["mean_latency"] - 0.2) < 1e-9


def test_build_report_writes_html_with_title(tmp_path: Path) -> None:
    trace = tmp_path / "skill_trace.jsonl"
    out = tmp_path / "report.html"
    entries = [
        {"sig": "a", "action": "click", "params": {}, "cached": False, "reward": 0.0},
        {"sig": "b", "action": "key_press", "params": {"key": "w"}, "cached": False, "reward": 1.0},
        {"sig": "c", "action": "noop", "params": {}, "cached": False, "reward": -0.5},
    ]
    _write_trace(trace, entries)

    build_report(trace, out)

    assert out.exists()
    html = out.read_text(encoding="utf-8")
    assert "<title>" in html


def test_build_report_surfaces_skipped_capture_frames(tmp_path: Path) -> None:
    """A near-black capture recorded as a 'skip' step shows in the report."""
    trace = tmp_path / "skill_trace.jsonl"
    out = tmp_path / "report.html"
    entries = [
        {
            "sig": "a",
            "action": "click",
            "params": {"button": "left"},
            "cached": False,
            "reward": 1.0,
        },
        {
            "sig": "black-frame",
            "action": "skip",
            "params": {"reason": "near-black capture", "non_black_ratio": 0.0},
            "cached": False,
            "reward": 0.0,
        },
    ]
    _write_trace(trace, entries)

    stats = build_report(trace, out)
    assert stats["steps"] == 2

    html = out.read_text(encoding="utf-8")
    # Skipped-step summary + the highlighted row are rendered.
    assert "Skipped Steps" in html
    assert "1" in html  # skipped count
    assert "near-black capture" in html
    assert "skip-row" in html
