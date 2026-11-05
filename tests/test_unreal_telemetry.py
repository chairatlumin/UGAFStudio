from __future__ import annotations

import json
import urllib.error
import urllib.request
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from app.database.database import QADatabase
from qa_framework.gameplay_agent.unreal_telemetry import (
    FMVCoverageLedger,
    TelemetryValidationError,
    UnrealTelemetryAdapter,
    UnrealTelemetryHTTPServer,
    validate_event,
)

PROFILE = "demo"
BUILD = "demo-build-7"
TOKEN = "test-token-that-is-at-least-24-chars"


def _event(sequence: int = 1, **overrides: object) -> dict[str, object]:
    now = datetime.now(UTC)
    payload: dict[str, object] = {
        "schema_version": 1,
        "profile": PROFILE,
        "build_id": BUILD,
        "event_id": f"evt-{sequence}",
        "sequence": sequence,
        "emitted_at_utc": now.isoformat(),
        "event_type": "choices_present",
        "state": {
            "scene_id": "HSB_Choice_01",
            "playback_seconds": 45.25,
            "subtitle": {"cue_id": "cue-1", "locale": "en-US", "text": "Choose."},
            "choice": {
                "group_id": "go-left",
                "options": [
                    {"id": f"choice-{index}", "text": f"Choice {index}", "visible": True}
                    for index in range(1, 5)
                ] + [{"id": "timeout", "text": "Wait", "visible": True, "kind": "timer"}],
                "timer_remaining_seconds": 8.0,
                "resolution": None,
            },
            "minigame": None,
        },
    }
    payload.update(overrides)
    return payload


def _post(url: str, payload: dict[str, object], token: str | None) -> tuple[int, dict[str, object]]:
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, json.dumps(payload).encode(), headers, method="POST")
    try:
        response = urllib.request.urlopen(request, timeout=2)
    except urllib.error.HTTPError as exc:
        response = exc
    with response:
        return response.status, json.loads(response.read())


def test_validator_captures_fmv_choices_subtitles_timeout_and_minigame() -> None:
    payload = _event()
    state = validate_event(payload, profile=PROFILE, build_id=BUILD)
    assert len(state.choice_options) == 5
    assert [option["id"] for option in state.choice_options[:4]] == [
        "choice-1", "choice-2", "choice-3", "choice-4"
    ]
    assert state.subtitle == {"cue_id": "cue-1", "locale": "en-US", "text": "Choose."}

    payload["state"]["choice"]["timer_remaining_seconds"] = 0  # type: ignore[index]
    payload["state"]["choice"]["resolution"] = {  # type: ignore[index]
        "choice_id": "timeout", "method": "timeout"
    }
    payload["state"]["minigame"] = {  # type: ignore[index]
        "name": "phone-puzzle", "state": "complete", "result": "win"
    }
    resolved = validate_event(payload, profile=PROFILE, build_id=BUILD)
    ledger = FMVCoverageLedger()
    ledger.observe(resolved)
    summary = ledger.summary()
    assert summary["qa_status"] == "UNASSERTED"
    assert summary["visible_choices"] == 5
    assert summary["timeout_branches"] == 1
    assert summary["minigame_results"] == 1


def test_validator_accepts_typed_unreal_performance_sample() -> None:
    payload = _event(event_type="performance_sample")
    payload["state"]["performance"] = {  # type: ignore[index]
        "scenario_id": "gpu-pressure",
        "phase": "spike",
        "metrics": {
            "frame_time_ms": 34.5,
            "gpu_ms": 22.1,
            "game_thread_ms": 6.0,
            "render_thread_ms": 5.2,
            "memory_mb": 4096,
            "draw_calls": 1800,
        },
    }
    state = validate_event(payload, profile=PROFILE, build_id=BUILD)
    assert state.performance == {
        "scenario_id": "gpu-pressure",
        "phase": "spike",
        "metrics": {
            "frame_time_ms": 34.5,
            "gpu_ms": 22.1,
            "game_thread_ms": 6.0,
            "render_thread_ms": 5.2,
            "memory_mb": 4096.0,
            "draw_calls": 1800.0,
        },
    }


@pytest.mark.parametrize(
    "performance,match",
    [
        ({"scenario_id": "gpu", "phase": "unknown", "metrics": {"frame_time_ms": 1}}, "phase"),
        ({"scenario_id": "gpu", "phase": "steady", "metrics": {"frame_time_ms": float("nan")}}, "finite"),
        ({"scenario_id": "gpu", "phase": "steady", "metrics": {"fps": 60}}, "frame_time_ms"),
    ],
)
def test_validator_rejects_invalid_performance_payload(performance: object, match: str) -> None:
    payload = _event(event_type="performance_sample")
    payload["state"]["performance"] = performance  # type: ignore[index]
    with pytest.raises(TelemetryValidationError, match=match):
        validate_event(payload, profile=PROFILE, build_id=BUILD)


@pytest.mark.parametrize("field,value", [
    ("profile", "other"),
    ("build_id", "old-build"),
    ("schema_version", 2),
])
def test_validator_fails_closed_for_profile_build_and_schema(field: str, value: object) -> None:
    with pytest.raises(TelemetryValidationError):
        validate_event(_event(**{field: value}), profile=PROFILE, build_id=BUILD)


def test_validator_rejects_stale_future_and_bad_timeout() -> None:
    now = datetime.now(UTC)
    stale = _event(emitted_at_utc=(now - timedelta(seconds=30)).isoformat())
    with pytest.raises(TelemetryValidationError, match="stale"):
        validate_event(stale, profile=PROFILE, build_id=BUILD, now=now)
    future = _event(emitted_at_utc=(now + timedelta(seconds=30)).isoformat())
    with pytest.raises(TelemetryValidationError, match="future"):
        validate_event(future, profile=PROFILE, build_id=BUILD, now=now)
    bad_timeout = _event()
    bad_timeout["state"]["choice"]["resolution"] = {  # type: ignore[index]
        "choice_id": "choice-1", "method": "timeout"
    }
    with pytest.raises(TelemetryValidationError, match="expired timer"):
        validate_event(bad_timeout, profile=PROFILE, build_id=BUILD)


def test_adapter_rejects_duplicates_reordering_and_records_sequence_gap() -> None:
    adapter = UnrealTelemetryAdapter(PROFILE, BUILD)
    assert adapter.ingest(_event(1))["accepted"] is True
    assert adapter.ingest(_event(1))["error"] == "duplicate event_id"
    assert adapter.ingest(_event(1, event_id="other-id"))["error"] == "out-of-order sequence"
    gap = adapter.ingest(_event(3))
    assert gap["accepted"] is True
    assert gap["sequence_gap"] == 1


def test_failed_persistence_does_not_commit_event_and_retry_succeeds() -> None:
    adapter = UnrealTelemetryAdapter(PROFILE, BUILD)
    payload = _event()
    failed = adapter.ingest(payload, persist=lambda _payload: False)
    assert failed["error"] == "event persistence failed"
    assert adapter.last_sequence == 0
    success = adapter.ingest(payload, persist=lambda _payload: True)
    assert success["accepted"] is True


def test_local_receiver_authenticates_and_persists_to_profile_database(tmp_path: Path) -> None:
    db = QADatabase(tmp_path / "qa.sqlite3")
    db.register_game(PROFILE, "Demo", "fmv")
    adapter = UnrealTelemetryAdapter(PROFILE, BUILD)
    receiver = UnrealTelemetryHTTPServer(
        adapter, TOKEN, port=0,
        persist=lambda event: db.record_unreal_telemetry_event(PROFILE, "run-1", event),
    )
    receiver.start_background()
    base = f"http://127.0.0.1:{receiver.address[1]}"
    try:
        health = urllib.request.urlopen(f"{base}/health", timeout=2)
        assert json.loads(health.read())["read_only"] is True
        unauthorized_status, _ = _post(f"{base}/v1/events", _event(), None)
        assert unauthorized_status == 401
        status, body = _post(f"{base}/v1/events", _event(), TOKEN)
        assert status == 202 and body["accepted"] is True
        stored = db.list_unreal_telemetry_events(PROFILE, "run-1")
        assert len(stored) == 1
        assert stored[0]["payload"]["state"]["scene_id"] == "HSB_Choice_01"
    finally:
        receiver.shutdown()


def test_performance_sample_round_trips_through_profile_database(tmp_path: Path) -> None:
    db = QADatabase(tmp_path / "qa.sqlite3")
    db.register_game(PROFILE, "Little Nightmares", "horror_platformer")
    payload = _event(event_type="performance_sample")
    payload["state"]["performance"] = {  # type: ignore[index]
        "scenario_id": "level-traversal",
        "phase": "recovery",
        "metrics": {"frame_time_ms": 27.1, "gpu_ms": 11.0, "memory_mb": 3000},
    }
    result = UnrealTelemetryAdapter(PROFILE, BUILD).ingest(
        payload, persist=lambda event: db.record_unreal_telemetry_event(PROFILE, "perf-1", event)
    )
    stored = db.list_unreal_telemetry_events(PROFILE, "perf-1")
    assert result["accepted"] is True
    assert stored[0]["payload"]["state"]["performance"]["scenario_id"] == "level-traversal"


def test_receiver_rejects_non_local_binding_and_database_failure_can_retry() -> None:
    with pytest.raises(ValueError, match="localhost"):
        UnrealTelemetryHTTPServer(UnrealTelemetryAdapter(PROFILE, BUILD), TOKEN, host="0.0.0.0")
    receiver = UnrealTelemetryHTTPServer(
        UnrealTelemetryAdapter(PROFILE, BUILD), TOKEN, port=0,
        persist=lambda _event: False,
    )
    thread = receiver.start_background()
    base = f"http://127.0.0.1:{receiver.address[1]}"
    try:
        status, body = _post(f"{base}/v1/events", _event(), TOKEN)
        assert status == 503 and body["accepted"] is False
        assert receiver._server.adapter.last_sequence == 0
    finally:
        receiver.shutdown()
        thread.join(timeout=2)
