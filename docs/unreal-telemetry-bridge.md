# Unreal telemetry bridge (WP-2)

The bridge is an optional, local-only, read-only evidence path for an Unreal FMV build. It receives events from a developer-enabled game client; it does not control input, inspect private Unreal objects, or modify the read-only game website. Black-box screen/OCR automation remains a separate path.

## Start the receiver

Register the game profile in UGAF Studio first. Open PowerShell in the repository and run:

```powershell
$env:UGAF_UNREAL_BRIDGE_TOKEN = [Convert]::ToBase64String([Security.Cryptography.RandomNumberGenerator]::GetBytes(32))
.\.venv\Scripts\python.exe scripts\unreal_telemetry_bridge.py `
  --profile highschoolblood-demo --build-id <exact-build-id> --session-id <unique-run-id> --port 8766
```

The secret remains in that PowerShell process environment. Keep the same value in the Unreal client configuration. The service binds only to `127.0.0.1` and accepts no gameplay commands. The default port is **8766**, so it runs beside the Robot Decision API on `127.0.0.1:8765`.

## Routes

- `GET /health`: unauthenticated readiness and schema version only.
- `GET /v1/state`: latest accepted state; bearer token required.
- `POST /v1/events`: append one event; bearer token required, JSON body limited to 64 KiB.

Every event must carry schema version 1, the exact profile and build ID, a unique event ID, monotonically increasing sequence, and a timezone-aware UTC timestamp no more than five seconds old. Duplicate IDs, reordered events, wrong profile/build, stale/future timestamps, malformed payloads, and unauthorized requests are rejected. Sequence gaps are accepted but returned as gaps. The event is acknowledged only after SQLite persistence succeeds.

## Event shape

```json
{
  "schema_version": 1,
  "profile": "highschoolblood-demo",
  "build_id": "<exact-build-id>",
  "event_id": "<unique-event-id>",
  "sequence": 1,
  "emitted_at_utc": "2026-10-11T10:00:00Z",
  "event_type": "choices_present",
  "state": {
    "scene_id": "HSB_Choice_01",
    "playback_seconds": 45.25,
    "subtitle": {"cue_id": "cue-123", "locale": "en-US", "text": "Choose."},
    "choice": {
      "group_id": "go-left",
      "options": [
        {"id": "choice-1", "text": "Option 1", "visible": true, "kind": "standard"},
        {"id": "choice-2", "text": "Option 2", "visible": true, "kind": "standard"},
        {"id": "choice-3", "text": "Option 3", "visible": true, "kind": "standard"},
        {"id": "choice-4", "text": "Option 4", "visible": true, "kind": "standard"},
        {"id": "timer", "text": "Wait", "visible": true, "kind": "timer"}
      ],
      "timer_remaining_seconds": 8.0,
      "resolution": null
    },
    "minigame": null
  }
}
```

For a stress sample, set `event_type` to `performance_sample` and add a typed
`state.performance` block. Allowed metric keys are `frame_time_ms` (required),
`fps`, `game_thread_ms`, `render_thread_ms`, `gpu_ms`, `memory_mb`,
`gpu_memory_mb`, `draw_calls`, `streaming_pool_used_mb`, and
`streaming_pool_budget_mb`. Values must be finite nonnegative numbers. Each
sample also needs a stable `scenario_id` and phase (`warmup`, `steady`, `spike`,
`recovery`, or `soak`).

```json
{
  "schema_version": 1,
  "profile": "little-nightmares",
  "build_id": "<exact-build-id>",
  "event_id": "<unique-event-id>",
  "sequence": 27,
  "emitted_at_utc": "2026-11-04T10:00:00Z",
  "event_type": "performance_sample",
  "state": {
    "scene_id": "LN_Level_01",
    "playback_seconds": 0,
    "performance": {
      "scenario_id": "gpu-pressure",
      "phase": "spike",
      "metrics": {
        "frame_time_ms": 34.5,
        "fps": 29.0,
        "game_thread_ms": 6.0,
        "render_thread_ms": 5.2,
        "gpu_ms": 22.1,
        "memory_mb": 4096,
        "gpu_memory_mb": 2048,
        "draw_calls": 1800,
        "streaming_pool_used_mb": 900,
        "streaming_pool_budget_mb": 1024
      }
    }
  }
}
```

Subsequent events should report the current snapshot; a resolved timeout uses `resolution: {"choice_id":"timer","method":"timeout"}` and must have timer remaining at zero. Resolution methods are `input`, `timeout`, or `system`. Minigame state may include `name`, `state`, and an optional result (`win`, `loss`, `draw`, `aborted`). A client should emit explicit states for scene changes, subtitles, choices, choice resolution, pause, playback, minigame state, and scene end.

## Storage and use

Events append to the selected profile database, in the `unreal_telemetry_events` table, partitioned by session and build. Read them with MCP `list_unreal_telemetry(profile, session_id, limit)`. Performance samples appear in Studio's `TA Optimize` Unreal-style frame-time graph and MCP `get_unreal_performance_report(profile, session_id, target_fps, scenario_id, baseline_session_id)`. The graph reports p95/mean frame time, hitches above twice the frame budget, CPU/GPU timing lanes, memory growth and streaming pressure. A baseline session adds matching-scenario signed deltas. Optimization suggestions are hypotheses to verify in Unreal Insights; analysis never modifies game settings or marks a testcase PASS.

## Integration boundary

An experimental Unreal runtime component is available in [`unreal/UGAFTelemetry`](../unreal/UGAFTelemetry/README.md). It emits frame-time P95 windows, derived FPS, and process physical-memory samples. The plugin compiled with Unreal Build Tool against a temporary host project on UE 5.7, but this repository does not contain the Demo's `.uproject` or client source, and no game runtime emission has been verified. The bridge cannot claim a game is instrumented until the component is installed in the target project and its events are accepted. Performance values must be captured in the game process; the Studio graph does not substitute desktop CPU or screen-preview measurements for Unreal stress evidence.
