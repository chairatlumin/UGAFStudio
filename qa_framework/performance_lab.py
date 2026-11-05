"""Unreal performance-stress telemetry analysis and optimization hints.

This module only analyzes recorded Unreal samples. It does not start or alter a
game stress test; samples must come from an instrumented Unreal build or an
explicitly imported telemetry export.
"""

from __future__ import annotations

import json
import math
import statistics
from datetime import datetime
from pathlib import Path
from typing import Any

STRESS_PROFILES: tuple[dict[str, Any], ...] = (
    {
        "id": "steady-state",
        "name": "Steady state",
        "phases": ["warmup", "steady"],
        "purpose": "Measure sustained frame-time and memory behavior at a fixed scene load.",
        "signals": ["frame_time_ms", "game_thread_ms", "render_thread_ms", "gpu_ms", "memory_mb"],
    },
    {
        "id": "gpu-pressure",
        "name": "GPU pressure",
        "phases": ["warmup", "steady", "spike", "recovery"],
        "purpose": "Observe GPU frame time under effects, lighting, and resolution pressure.",
        "signals": ["frame_time_ms", "gpu_ms", "draw_calls", "gpu_memory_mb"],
    },
    {
        "id": "actor-density",
        "name": "Actor density",
        "phases": ["warmup", "steady", "spike", "recovery"],
        "purpose": "Compare game-thread and render-thread cost as scene actor load rises.",
        "signals": ["frame_time_ms", "game_thread_ms", "render_thread_ms", "draw_calls"],
    },
    {
        "id": "streaming-soak",
        "name": "Streaming and memory soak",
        "phases": ["warmup", "soak", "recovery"],
        "purpose": "Track memory and texture-streaming pool pressure during a long traversal.",
        "signals": ["memory_mb", "gpu_memory_mb", "streaming_pool_used_mb", "streaming_pool_budget_mb"],
    },
    {
        "id": "level-traversal",
        "name": "Level traversal",
        "phases": ["warmup", "steady", "spike", "recovery"],
        "purpose": "Find traversal hitches and recovery time across level transitions.",
        "signals": ["frame_time_ms", "fps", "memory_mb", "streaming_pool_used_mb"],
    },
)


def _percentile(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * percentile
    low = math.floor(position)
    high = math.ceil(position)
    if low == high:
        return ordered[low]
    weight = position - low
    return ordered[low] * (1 - weight) + ordered[high] * weight


def _sample_payload(event: dict[str, Any]) -> tuple[dict[str, Any] | None, bool]:
    payload = event.get("payload", event)
    state = payload.get("state") if isinstance(payload, dict) else None
    performance = state.get("performance") if isinstance(state, dict) else None
    if not isinstance(performance, dict) or not isinstance(performance.get("metrics"), dict):
        return None, False
    if not isinstance(payload, dict) or payload.get("event_type") != "performance_sample":
        return None, True
    sequence = payload.get("sequence")
    emitted_at = payload.get("emitted_at_utc")
    build_id = payload.get("build_id")
    scene_id = state.get("scene_id") if isinstance(state, dict) else None
    if (
        isinstance(sequence, bool) or not isinstance(sequence, int) or sequence < 1
        or not isinstance(build_id, str) or not build_id.strip()
        or not isinstance(scene_id, str) or not scene_id.strip()
        or not isinstance(emitted_at, str)
    ):
        return None, True
    try:
        timestamp = datetime.fromisoformat(emitted_at.replace("Z", "+00:00"))
    except ValueError:
        return None, True
    if timestamp.tzinfo is None:
        return None, True
    metrics = performance["metrics"]
    known_metrics = {
        "frame_time_ms", "fps", "game_thread_ms", "render_thread_ms", "gpu_ms",
        "memory_mb", "gpu_memory_mb", "draw_calls", "streaming_pool_used_mb",
        "streaming_pool_budget_mb",
    }
    scenario_id = performance.get("scenario_id")
    phase = performance.get("phase")
    if (
        not isinstance(scenario_id, str) or not scenario_id.strip()
        or phase not in {"warmup", "steady", "spike", "recovery", "soak"}
        or "frame_time_ms" not in metrics or set(metrics) - known_metrics
    ):
        return None, True
    if any(
        isinstance(value, bool) or not isinstance(value, (int, float))
        or not math.isfinite(float(value)) or float(value) < 0
        for value in metrics.values()
    ):
        return None, True
    return {
        "sequence": sequence,
        "emitted_at_utc": emitted_at,
        "build_id": build_id,
        "scene_id": scene_id,
        **performance,
    }, False


def analyze_performance_events(
    events: list[dict[str, Any]], *, profile: str, session_id: str = "",
    target_fps: float = 60.0, scenario_id: str = "",
) -> dict[str, Any]:
    """Summarize validated persisted events; all conclusions remain advisory."""
    if isinstance(target_fps, bool) or not isinstance(target_fps, (int, float)):
        raise ValueError("target_fps must be numeric")
    target = float(target_fps)
    if not math.isfinite(target) or not 1 <= target <= 1000:
        raise ValueError("target_fps must be finite and within 1..1000")

    samples: list[dict[str, Any]] = []
    rejected_samples = 0
    for event in events:
        sample, rejected = _sample_payload(event)
        rejected_samples += int(rejected)
        if sample is not None and (not scenario_id or sample["scenario_id"] == scenario_id):
            samples.append(sample)
    samples.sort(key=lambda sample: (int(sample["sequence"]), str(sample["emitted_at_utc"])))
    budget_ms = 1000.0 / target
    frame_times = [float(sample["metrics"]["frame_time_ms"]) for sample in samples]
    metrics: dict[str, dict[str, float | None]] = {}
    for key in (
        "fps", "frame_time_ms", "game_thread_ms", "render_thread_ms", "gpu_ms",
        "memory_mb", "gpu_memory_mb", "draw_calls", "streaming_pool_used_mb",
        "streaming_pool_budget_mb",
    ):
        values = [float(sample["metrics"][key]) for sample in samples if key in sample["metrics"]]
        if values:
            metrics[key] = {
                "min": min(values),
                "mean": statistics.fmean(values),
                "p95": _percentile(values, 0.95),
                "max": max(values),
                "first": values[0],
                "last": values[-1],
            }

    hitches = sum(value > budget_ms * 2 for value in frame_times)
    p95_frame = _percentile(frame_times, 0.95)
    mean_frame = statistics.fmean(frame_times) if frame_times else None
    frame_budget_met = p95_frame is not None and p95_frame <= budget_ms
    diagnosis: list[dict[str, str]] = []
    if not samples:
        diagnosis.append({
            "kind": "missing_data", "finding": "No Unreal performance samples were found.",
            "next_step": "Run an instrumented Unreal stress scenario and send performance_sample events.",
        })
    else:
        thread_costs = {
            name: metrics[name]["mean"]
            for name in ("game_thread_ms", "render_thread_ms", "gpu_ms")
            if name in metrics and metrics[name]["mean"] is not None
        }
        if thread_costs:
            dominant = max(thread_costs, key=lambda name: float(thread_costs[name]))
            if float(thread_costs[dominant]) >= budget_ms * 0.70:
                diagnosis.append({
                    "kind": "bottleneck_hypothesis",
                    "finding": f"{dominant.replace('_ms', '').replace('_', ' ')} time dominates the target frame budget.",
                    "next_step": "Profile this lane in Unreal Insights before changing content or code.",
                })
        memory = metrics.get("memory_mb")
        if memory and len(samples) >= 2 and memory["last"] > memory["first"] * 1.05:
            diagnosis.append({
                "kind": "memory_growth", "finding": "Process memory rose by more than 5% during this session.",
                "next_step": "Repeat the same soak duration and inspect allocation/streaming captures for retained growth.",
            })
        used = metrics.get("streaming_pool_used_mb")
        capacity = metrics.get("streaming_pool_budget_mb")
        if used and capacity and capacity["mean"] and used["p95"] is not None:
            if used["p95"] / capacity["mean"] >= 0.9:
                diagnosis.append({
                    "kind": "streaming_pressure", "finding": "P95 texture streaming pool use reaches at least 90% of its mean budget.",
                    "next_step": "Inspect mip requests and streaming pool warnings during the same traversal.",
                })
        if p95_frame is not None and not frame_budget_met:
            diagnosis.append({
                "kind": "frame_budget", "finding": f"P95 frame time exceeds the {target:g} FPS budget.",
                "next_step": "Compare spike and steady phases to locate when the frame budget is lost.",
            })

    return {
        "schema_version": 1,
        "report_type": "unreal_performance_stress_analysis",
        "profile": profile,
        "session_id": session_id,
        "scenario_id": scenario_id,
        "build_ids": sorted({str(sample["build_id"]) for sample in samples if sample["build_id"]}),
        "sample_count": len(samples),
        "rejected_performance_samples": rejected_samples,
        "source": "unreal_telemetry_events" if events else "none",
        "target_fps": target,
        "frame_budget_ms": budget_ms,
        "p95_frame_time_ms": p95_frame,
        "mean_frame_time_ms": mean_frame,
        "hitch_count_over_2x_budget": hitches,
        "frame_budget_met": frame_budget_met if samples else None,
        "metrics": metrics,
        "samples": samples,
        "diagnosis": diagnosis,
        "qa_status": "UNASSERTED",
        "note": "Performance observations and optimization hints do not prove a testcase or game requirement passed.",
    }


def compare_performance_reports(
    baseline: dict[str, Any], candidate: dict[str, Any]
) -> dict[str, Any]:
    """Compare matching Unreal stress scenarios without converting deltas to QA pass."""
    for field in ("profile", "scenario_id", "target_fps"):
        if baseline.get(field) != candidate.get(field):
            raise ValueError(f"baseline and candidate {field} must match")
    deltas: dict[str, dict[str, float | None]] = {}
    for metric in sorted(set(baseline.get("metrics", {})) & set(candidate.get("metrics", {}))):
        deltas[metric] = {}
        for statistic in ("mean", "p95", "max"):
            before = baseline["metrics"][metric].get(statistic)
            after = candidate["metrics"][metric].get(statistic)
            if before is None or after is None:
                deltas[metric][statistic] = None
                continue
            difference = float(after) - float(before)
            delta_percent = difference / float(before) * 100 if float(before) else None
            deltas[metric][f"{statistic}_delta"] = difference
            deltas[metric][f"{statistic}_delta_percent"] = delta_percent
    before_p95 = baseline.get("p95_frame_time_ms")
    after_p95 = candidate.get("p95_frame_time_ms")
    if before_p95 is None or after_p95 is None:
        verdict = "insufficient_samples"
    elif after_p95 < before_p95:
        verdict = "lower_p95_frame_time_observed"
    elif after_p95 > before_p95:
        verdict = "higher_p95_frame_time_observed"
    else:
        verdict = "unchanged_p95_frame_time_observed"
    return {
        "baseline_session_id": baseline.get("session_id", ""),
        "candidate_session_id": candidate.get("session_id", ""),
        "baseline_build_ids": baseline.get("build_ids", []),
        "candidate_build_ids": candidate.get("build_ids", []),
        "scenario_id": baseline.get("scenario_id", ""),
        "target_fps": baseline.get("target_fps"),
        "p95_frame_time_delta_ms": (
            float(after_p95) - float(before_p95)
            if before_p95 is not None and after_p95 is not None
            else None
        ),
        "observation": verdict,
        "metric_deltas": deltas,
        "qa_status": "UNASSERTED",
        "note": "Observed session deltas are not causal proof; compare matching game build, scene, and settings.",
    }


def export_performance_report(report: dict[str, Any], destination: Path) -> Path:
    """Write a deterministic JSON report without replacing an existing artifact."""
    path = Path(destination)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise FileExistsError(f"Report already exists: {path}")
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)
    return path
