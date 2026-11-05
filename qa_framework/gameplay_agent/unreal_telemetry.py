"""Read-only Unreal telemetry contract, validator, route ledger, and localhost receiver."""

from __future__ import annotations

import hmac
import json
import math
import threading
from collections import deque
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable

_EVENT_TYPES = frozenset({
    "heartbeat", "scene_started", "playback", "subtitle", "choices_present",
    "choice_resolved", "minigame_state", "scene_ended", "game_paused",
    "performance_sample",
})
_PERFORMANCE_METRICS = frozenset({
    "frame_time_ms", "fps", "game_thread_ms", "render_thread_ms", "gpu_ms",
    "memory_mb", "gpu_memory_mb", "draw_calls", "streaming_pool_used_mb",
    "streaming_pool_budget_mb",
})
_CHOICE_KINDS = frozenset({"standard", "timer"})
_CHOICE_METHODS = frozenset({"input", "timeout", "system"})
_MINIGAME_RESULTS = frozenset({"win", "loss", "draw", "aborted"})


class TelemetryValidationError(ValueError):
    """Raised when an event violates the versioned read-only telemetry contract."""


@dataclass(frozen=True)
class TelemetryState:
    profile: str
    build_id: str
    event_id: str
    sequence: int
    emitted_at_utc: str
    event_type: str
    scene_id: str
    playback_seconds: float
    subtitle: dict[str, str] | None
    choice_group_id: str
    choice_options: tuple[dict[str, Any], ...]
    choice_timer_remaining_seconds: float | None
    choice_resolution: dict[str, str] | None
    minigame: dict[str, Any] | None
    performance: dict[str, Any] | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _required_text(value: Any, field: str, max_length: int = 256) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > max_length:
        raise TelemetryValidationError(f"{field} must be nonempty text up to {max_length} chars")
    return value.strip()


def _finite_number(value: Any, field: str, *, minimum: float = 0.0) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TelemetryValidationError(f"{field} must be a number")
    number = float(value)
    if not math.isfinite(number) or number < minimum:
        raise TelemetryValidationError(f"{field} must be finite and >= {minimum}")
    return number


def _parse_timestamp(value: Any) -> datetime:
    text = _required_text(value, "emitted_at_utc", 64)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise TelemetryValidationError("emitted_at_utc must be ISO-8601") from exc
    if parsed.tzinfo is None:
        raise TelemetryValidationError("emitted_at_utc must include a timezone")
    return parsed.astimezone(UTC)


def validate_event(
    payload: Any, *, profile: str, build_id: str, now: datetime | None = None,
    max_age: timedelta = timedelta(seconds=5), future_skew: timedelta = timedelta(seconds=2),
) -> TelemetryState:
    """Validate one complete UE snapshot event without producing gameplay input."""
    if not isinstance(payload, dict):
        raise TelemetryValidationError("event must be an object")
    if payload.get("schema_version") != 1:
        raise TelemetryValidationError("unsupported schema_version")
    event_profile = _required_text(payload.get("profile"), "profile", 100)
    if event_profile != profile:
        raise TelemetryValidationError("profile mismatch")
    event_build = _required_text(payload.get("build_id"), "build_id", 100)
    if event_build != build_id:
        raise TelemetryValidationError("build_id mismatch")
    event_id = _required_text(payload.get("event_id"), "event_id", 128)
    sequence = payload.get("sequence")
    if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence < 1:
        raise TelemetryValidationError("sequence must be a positive integer")
    emitted = _parse_timestamp(payload.get("emitted_at_utc"))
    current = now or datetime.now(UTC)
    age = current.astimezone(UTC) - emitted
    if age > max_age:
        raise TelemetryValidationError("event is stale")
    if age < -future_skew:
        raise TelemetryValidationError("event timestamp is in the future")

    event_type = _required_text(payload.get("event_type"), "event_type", 40)
    if event_type not in _EVENT_TYPES:
        raise TelemetryValidationError("unsupported event_type")
    raw_state = payload.get("state")
    if not isinstance(raw_state, dict):
        raise TelemetryValidationError("state must be an object")
    scene_id = _required_text(raw_state.get("scene_id"), "state.scene_id", 256)
    playback_seconds = _finite_number(
        raw_state.get("playback_seconds", 0), "state.playback_seconds"
    )

    subtitle_value = raw_state.get("subtitle")
    subtitle: dict[str, str] | None = None
    if subtitle_value is not None:
        if not isinstance(subtitle_value, dict):
            raise TelemetryValidationError("state.subtitle must be an object or null")
        subtitle = {
            "cue_id": _required_text(subtitle_value.get("cue_id"), "subtitle.cue_id", 256),
            "locale": _required_text(subtitle_value.get("locale"), "subtitle.locale", 24),
            "text": _required_text(subtitle_value.get("text"), "subtitle.text", 4096),
        }

    raw_choice = raw_state.get("choice")
    group_id = ""
    options: tuple[dict[str, Any], ...] = ()
    timer_remaining: float | None = None
    resolution: dict[str, str] | None = None
    if raw_choice is not None:
        if not isinstance(raw_choice, dict):
            raise TelemetryValidationError("state.choice must be an object or null")
        group_id = _required_text(raw_choice.get("group_id"), "choice.group_id", 256)
        raw_options = raw_choice.get("options")
        if not isinstance(raw_options, list) or not 1 <= len(raw_options) <= 32:
            raise TelemetryValidationError("choice.options must contain 1..32 options")
        option_ids: set[str] = set()
        normalized_options: list[dict[str, Any]] = []
        for index, option in enumerate(raw_options):
            if not isinstance(option, dict):
                raise TelemetryValidationError(f"choice.options[{index}] must be an object")
            option_id = _required_text(option.get("id"), f"choice.options[{index}].id", 128)
            if option_id in option_ids:
                raise TelemetryValidationError("choice option IDs must be unique")
            option_ids.add(option_id)
            kind = _required_text(option.get("kind", "standard"), "choice option kind", 20)
            if kind not in _CHOICE_KINDS:
                raise TelemetryValidationError("choice option kind is unsupported")
            visible = option.get("visible")
            if not isinstance(visible, bool):
                raise TelemetryValidationError("choice option visible must be boolean")
            normalized_options.append({
                "id": option_id,
                "text": str(option.get("text", ""))[:512],
                "visible": visible,
                "kind": kind,
            })
        options = tuple(normalized_options)
        remaining = raw_choice.get("timer_remaining_seconds")
        if remaining is not None:
            timer_remaining = _finite_number(remaining, "choice.timer_remaining_seconds")
        raw_resolution = raw_choice.get("resolution")
        if raw_resolution is not None:
            if not isinstance(raw_resolution, dict):
                raise TelemetryValidationError("choice.resolution must be an object or null")
            selected_id = _required_text(raw_resolution.get("choice_id"), "resolution.choice_id", 128)
            method = _required_text(raw_resolution.get("method"), "resolution.method", 20)
            if method not in _CHOICE_METHODS:
                raise TelemetryValidationError("choice resolution method is unsupported")
            selected = next((item for item in options if item["id"] == selected_id), None)
            if selected is None:
                raise TelemetryValidationError("resolved choice_id is not in the option list")
            if method == "timeout" and (timer_remaining is None or timer_remaining > 0):
                raise TelemetryValidationError("timeout resolution requires an expired timer")
            if method == "timeout" and selected["kind"] != "timer":
                raise TelemetryValidationError("timeout resolution must select a timer option")
            resolution = {"choice_id": selected_id, "method": method}

    raw_minigame = raw_state.get("minigame")
    minigame: dict[str, Any] | None = None
    if raw_minigame is not None:
        if not isinstance(raw_minigame, dict):
            raise TelemetryValidationError("state.minigame must be an object or null")
        name = _required_text(raw_minigame.get("name"), "minigame.name", 256)
        state = _required_text(raw_minigame.get("state"), "minigame.state", 64)
        result = raw_minigame.get("result")
        if result is not None and result not in _MINIGAME_RESULTS:
            raise TelemetryValidationError("minigame.result is unsupported")
        minigame = {"name": name, "state": state, "result": result}

    raw_performance = raw_state.get("performance")
    performance: dict[str, Any] | None = None
    if raw_performance is not None and event_type != "performance_sample":
        raise TelemetryValidationError("state.performance is only valid for performance_sample events")
    if raw_performance is not None:
        if not isinstance(raw_performance, dict):
            raise TelemetryValidationError("state.performance must be an object or null")
        scenario_id = _required_text(
            raw_performance.get("scenario_id"), "performance.scenario_id", 128
        )
        phase = _required_text(raw_performance.get("phase"), "performance.phase", 32)
        if phase not in {"warmup", "steady", "spike", "recovery", "soak"}:
            raise TelemetryValidationError("performance.phase is unsupported")
        raw_metrics = raw_performance.get("metrics")
        if not isinstance(raw_metrics, dict) or not raw_metrics:
            raise TelemetryValidationError("performance.metrics must be a nonempty object")
        unknown_metrics = set(raw_metrics) - _PERFORMANCE_METRICS
        if unknown_metrics:
            raise TelemetryValidationError(
                f"unsupported performance metrics: {', '.join(sorted(unknown_metrics))}"
            )
        metrics = {
            key: _finite_number(value, f"performance.metrics.{key}")
            for key, value in raw_metrics.items()
        }
        if "frame_time_ms" not in metrics:
            raise TelemetryValidationError("performance.metrics.frame_time_ms is required")
        performance = {"scenario_id": scenario_id, "phase": phase, "metrics": metrics}
    elif event_type == "performance_sample":
        raise TelemetryValidationError("performance_sample requires state.performance")

    return TelemetryState(
        profile=event_profile, build_id=event_build, event_id=event_id,
        sequence=sequence, emitted_at_utc=emitted.isoformat(), event_type=event_type,
        scene_id=scene_id, playback_seconds=playback_seconds, subtitle=subtitle,
        choice_group_id=group_id, choice_options=options,
        choice_timer_remaining_seconds=timer_remaining,
        choice_resolution=resolution, minigame=minigame, performance=performance,
    )


class UnrealTelemetryAdapter:
    """Profile/build-scoped event gate with duplicate, reorder and stale checks."""

    def __init__(
        self, profile: str, build_id: str, *, clock: Callable[[], datetime] | None = None,
        max_age_seconds: float = 5.0, future_skew_seconds: float = 2.0,
    ) -> None:
        self.profile = profile
        self.build_id = build_id
        self._clock = clock or (lambda: datetime.now(UTC))
        self._max_age = timedelta(seconds=max_age_seconds)
        self._future_skew = timedelta(seconds=future_skew_seconds)
        self._last_sequence = 0
        self._last_timestamp: datetime | None = None
        self._seen: deque[str] = deque(maxlen=2048)
        self._seen_set: set[str] = set()
        self._lock = threading.Lock()
        self.latest: TelemetryState | None = None

    @property
    def last_sequence(self) -> int:
        return self._last_sequence

    def ingest(
        self, payload: Any,
        persist: Callable[[dict[str, Any]], bool] | None = None,
    ) -> dict[str, Any]:
        try:
            state = validate_event(
                payload, profile=self.profile, build_id=self.build_id, now=self._clock(),
                max_age=self._max_age, future_skew=self._future_skew,
            )
        except TelemetryValidationError as exc:
            return {"accepted": False, "error": str(exc), "state": None}
        timestamp = _parse_timestamp(state.emitted_at_utc)
        with self._lock:
            if state.event_id in self._seen_set:
                return {"accepted": False, "error": "duplicate event_id", "state": None}
            if state.sequence <= self._last_sequence:
                return {"accepted": False, "error": "out-of-order sequence", "state": None}
            if self._last_timestamp is not None and timestamp < self._last_timestamp:
                return {"accepted": False, "error": "event timestamp moved backwards", "state": None}
            gap = max(0, state.sequence - self._last_sequence - 1)
            if persist is not None:
                try:
                    persisted = bool(persist(payload))
                except Exception:
                    persisted = False
                if not persisted:
                    return {"accepted": False, "error": "event persistence failed", "state": None}
            if len(self._seen) == self._seen.maxlen:
                evicted = self._seen[0]
                self._seen_set.discard(evicted)
            self._seen.append(state.event_id)
            self._seen_set.add(state.event_id)
            self._last_sequence = state.sequence
            self._last_timestamp = timestamp
            self.latest = state
        return {"accepted": True, "sequence_gap": gap, "state": state.to_dict()}


class FMVCoverageLedger:
    """Observed coverage only; never upgrades telemetry into a testcase PASS."""

    def __init__(self) -> None:
        self.scenes: set[str] = set()
        self.subtitle_cues: set[tuple[str, str, str]] = set()
        self.visible_choices: set[tuple[str, str, str]] = set()
        self.resolved_choices: set[tuple[str, str, str, str]] = set()
        self.timeout_branches: set[tuple[str, str, str]] = set()
        self.minigame_states: set[tuple[str, str, str]] = set()
        self.minigame_results: set[tuple[str, str, str]] = set()

    def observe(self, state: TelemetryState) -> None:
        self.scenes.add(state.scene_id)
        if state.subtitle:
            self.subtitle_cues.add((
                state.scene_id, state.subtitle["cue_id"], state.subtitle["locale"]
            ))
        for option in state.choice_options:
            if option["visible"]:
                self.visible_choices.add((state.scene_id, state.choice_group_id, option["id"]))
        if state.choice_resolution:
            choice_id = state.choice_resolution["choice_id"]
            method = state.choice_resolution["method"]
            self.resolved_choices.add((
                state.scene_id, state.choice_group_id, choice_id, method
            ))
            if method == "timeout":
                self.timeout_branches.add((state.scene_id, state.choice_group_id, choice_id))
        if state.minigame:
            game = state.minigame
            self.minigame_states.add((state.scene_id, game["name"], game["state"]))
            if game.get("result"):
                self.minigame_results.add((state.scene_id, game["name"], game["result"]))

    def summary(self) -> dict[str, Any]:
        return {
            "qa_status": "UNASSERTED",
            "observed_scenes": len(self.scenes),
            "subtitle_cues": len(self.subtitle_cues),
            "visible_choices": len(self.visible_choices),
            "resolved_choices": len(self.resolved_choices),
            "timeout_branches": len(self.timeout_branches),
            "minigame_states": len(self.minigame_states),
            "minigame_results": len(self.minigame_results),
            "scenes": sorted(self.scenes),
        }


class _BridgeHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(
        self, address: tuple[str, int], adapter: UnrealTelemetryAdapter,
        bearer_token: str, persist: Callable[[dict[str, Any]], bool] | None,
    ) -> None:
        self.adapter = adapter
        self.bearer_token = bearer_token
        self.persist = persist
        super().__init__(address, _BridgeRequestHandler)


class _BridgeRequestHandler(BaseHTTPRequestHandler):
    server: _BridgeHTTPServer

    def log_message(self, _format: str, *args: Any) -> None:
        # Avoid logging request headers or token material.
        return

    def _send(self, status: int, body: dict[str, Any]) -> None:
        payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(payload)

    def _authorized(self) -> bool:
        header = self.headers.get("Authorization", "")
        expected = f"Bearer {self.server.bearer_token}"
        return hmac.compare_digest(header, expected)

    def do_GET(self) -> None:  # noqa: N802 - stdlib handler method
        if self.path == "/health":
            self._send(200, {
                "service": "ugaf-unreal-telemetry", "schema_version": 1,
                "profile": self.server.adapter.profile, "read_only": True,
            })
            return
        if self.path != "/v1/state":
            self._send(404, {"error": "not found"})
            return
        if not self._authorized():
            self._send(401, {"error": "unauthorized"})
            return
        latest = self.server.adapter.latest
        self._send(200, {"state": latest.to_dict() if latest else None})

    def do_POST(self) -> None:  # noqa: N802 - stdlib handler method
        if self.path != "/v1/events":
            self._send(404, {"error": "not found"})
            return
        if not self._authorized():
            self._send(401, {"error": "unauthorized"})
            return
        length_text = self.headers.get("Content-Length", "")
        try:
            length = int(length_text)
        except ValueError:
            self._send(400, {"error": "invalid Content-Length"})
            return
        if length < 1 or length > 65536:
            self._send(413, {"error": "event body must be 1..65536 bytes"})
            return
        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._send(400, {"error": "invalid JSON"})
            return
        result = self.server.adapter.ingest(payload, persist=self.server.persist)
        if not result["accepted"]:
            if result["error"] == "event persistence failed":
                self._send(503, result)
                return
            self._send(422, result)
            return
        self._send(202, {
            "accepted": True, "sequence_gap": result["sequence_gap"],
            "state": result["state"],
        })


class UnrealTelemetryHTTPServer:
    """Localhost-only bearer-token receiver; it has no route that can control the game."""

    def __init__(
        self, adapter: UnrealTelemetryAdapter, bearer_token: str, *, host: str = "127.0.0.1",
        port: int = 8766, persist: Callable[[dict[str, Any]], bool] | None = None,
    ) -> None:
        if host not in {"127.0.0.1", "localhost", "::1"}:
            raise ValueError("Unreal telemetry receiver may bind only to localhost")
        if len(bearer_token) < 24:
            raise ValueError("bearer token must be at least 24 characters")
        self._server = _BridgeHTTPServer((host, port), adapter, bearer_token, persist)

    @property
    def address(self) -> tuple[str, int]:
        return self._server.server_address[:2]

    def serve_forever(self) -> None:
        self._server.serve_forever()

    def start_background(self) -> threading.Thread:
        thread = threading.Thread(target=self.serve_forever, name="ugaf-unreal-bridge", daemon=True)
        thread.start()
        return thread

    def shutdown(self) -> None:
        self._server.shutdown()
        self._server.server_close()
