from __future__ import annotations

import json
from pathlib import Path

import pytest

from qa_framework.performance_lab import (
    analyze_performance_events,
    compare_performance_reports,
    export_performance_report,
)


def event(sequence: int, frame_ms: float, *, scenario: str = "steady-state") -> dict[str, object]:
    return {
        "profile": "little-nightmares",
        "session_id": "stress-001",
        "payload": {
            "sequence": sequence,
            "build_id": "dev-42",
            "event_type": "performance_sample",
            "emitted_at_utc": f"2026-11-04T12:00:{sequence:02d}+00:00",
            "state": {
                "scene_id": "LN_Level_01",
                "performance": {
                    "scenario_id": scenario,
                    "phase": "steady",
                    "metrics": {
                        "frame_time_ms": frame_ms,
                        "fps": 1000 / frame_ms,
                        "game_thread_ms": 4.0,
                        "render_thread_ms": 5.0,
                        "gpu_ms": 18.0 if frame_ms > 25 else 7.0,
                        "memory_mb": 1000 + sequence * 20,
                        "streaming_pool_used_mb": 900,
                        "streaming_pool_budget_mb": 1000,
                    },
                },
            },
        },
    }


def test_performance_analysis_finds_frame_budget_and_gpu_hypothesis() -> None:
    report = analyze_performance_events(
        [event(1, 10), event(5, 45), event(10, 42)],
        profile="little-nightmares",
        session_id="stress-001",
        scenario_id="steady-state",
        target_fps=60,
    )

    assert report["sample_count"] == 3
    assert report["build_ids"] == ["dev-42"]
    assert report["frame_budget_met"] is False
    assert report["hitch_count_over_2x_budget"] == 2
    kinds = {finding["kind"] for finding in report["diagnosis"]}
    assert {"bottleneck_hypothesis", "memory_growth", "frame_budget"} <= kinds
    assert report["qa_status"] == "UNASSERTED"


def test_analysis_filters_scenario_and_rejects_invalid_imported_metrics() -> None:
    bad = event(2, 10)
    bad["payload"]["state"]["performance"]["metrics"]["gpu_ms"] = float("nan")  # type: ignore[index]
    report = analyze_performance_events(
        [event(1, 12, scenario="gpu-pressure"), event(3, 14), bad],
        profile="little-nightmares",
        scenario_id="steady-state",
    )

    assert report["sample_count"] == 1
    assert report["rejected_performance_samples"] == 1
    assert report["samples"][0]["sequence"] == 3


def test_report_export_preserves_existing_artifact(tmp_path: Path) -> None:
    report = analyze_performance_events([], profile="little-nightmares")
    destination = tmp_path / "report.json"
    assert export_performance_report(report, destination) == destination
    assert json.loads(destination.read_text(encoding="utf-8"))["qa_status"] == "UNASSERTED"
    with pytest.raises(FileExistsError):
        export_performance_report(report, destination)


def test_target_fps_must_be_finite_and_bounded() -> None:
    with pytest.raises(ValueError, match="target_fps"):
        analyze_performance_events([], profile="x", target_fps=float("inf"))


def test_comparison_requires_matching_scenario_and_reports_observed_deltas() -> None:
    baseline = analyze_performance_events(
        [event(1, 30), event(2, 32)],
        profile="little-nightmares",
        session_id="before",
        scenario_id="steady-state",
    )
    candidate = analyze_performance_events(
        [event(1, 20), event(2, 22)],
        profile="little-nightmares",
        session_id="after",
        scenario_id="steady-state",
    )
    compared = compare_performance_reports(baseline, candidate)
    assert compared["observation"] == "lower_p95_frame_time_observed"
    assert compared["p95_frame_time_delta_ms"] < 0
    assert compared["qa_status"] == "UNASSERTED"
    with pytest.raises(ValueError, match="scenario_id"):
        compare_performance_reports(
            baseline,
            analyze_performance_events(
                [event(1, 20)], profile="little-nightmares", scenario_id="gpu-pressure"
            ),
        )


def test_mcp_performance_tool_returns_report_and_baseline_comparison(monkeypatch) -> None:
    class FakeDatabase:
        def list_unreal_telemetry_events(self, _profile: str, session_id: str, _limit: int):
            frame_time = 30 if session_id == "before" else 20
            return [event(1, frame_time)]

    monkeypatch.setattr(
        "app.database.database.QADatabase.for_profile",
        classmethod(lambda _cls, _profile: FakeDatabase()),
    )
    from qa_framework.mcp_tools import get_unreal_performance_report_tool

    report = get_unreal_performance_report_tool(
        profile="little-nightmares",
        session_id="after",
        baseline_session_id="before",
        scenario_id="steady-state",
    )
    assert report["sample_count"] == 1
    assert report["comparison"]["observation"] == "lower_p95_frame_time_observed"
