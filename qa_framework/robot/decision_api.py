"""Local HTTP decision API backed by UGAF's fail-closed VLM action validator."""

from __future__ import annotations

import argparse
import base64
import binascii
import hashlib
import json
import os
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

import numpy as np
from PIL import Image, UnidentifiedImageError

from qa_framework.gameplay_agent.backends import OpenAICompatBackend
from qa_framework.gameplay_agent.vlm_agent import VLMAgent

API_VERSION = "1"
DEFAULT_ACTIONS = ("noop", "click", "key_press")
SUPPORTED_ACTIONS = frozenset(DEFAULT_ACTIONS)
MAX_IMAGE_BYTES = 8 * 1024 * 1024
MAX_CONTEXT_CHARS = 8_000


def decode_frame(payload: Any) -> np.ndarray:
    """Decode and validate a base64 PNG/JPEG frame from an API request."""
    if not isinstance(payload, str) or not payload:
        raise ValueError("image_base64 is required.")
    if len(payload) > (MAX_IMAGE_BYTES * 4 // 3 + 8):
        raise ValueError("Image exceeds the request size limit.")
    try:
        encoded = base64.b64decode(payload, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("image_base64 is not valid base64.") from exc
    if not encoded or len(encoded) > MAX_IMAGE_BYTES:
        raise ValueError("Image is empty or exceeds the request size limit.")
    try:
        import io

        with Image.open(io.BytesIO(encoded)) as image:
            if image.format not in {"PNG", "JPEG"}:
                raise ValueError("Image must be PNG or JPEG.")
            width, height = image.size
            if width > 3840 or height > 2160 or width * height > 8_294_400:
                raise ValueError("Image dimensions exceed 3840x2160.")
            rgb = np.asarray(image.convert("RGB"))
    except (UnidentifiedImageError, OSError) as exc:
        raise ValueError("Image must be a decodable PNG or JPEG.") from exc
    return rgb[:, :, ::-1].copy()


class DecisionService:
    """Make one validated VLM decision for a single supplied frame."""

    def __init__(
        self,
        *,
        base_url: str = "http://127.0.0.1:1234/v1",
        api_key: str = "lm-studio",
        model: str = "qwen/qwen2.5-vl-7b",
        timeout: float = 45.0,
        backend: Any | None = None,
    ) -> None:
        if (not base_url and backend is None) or not model:
            raise ValueError("A VLM base URL and model are required.")
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self._backend = backend or OpenAICompatBackend(
            base_url=base_url,
            api_key=api_key,
            model=model,
            timeout=timeout,
            structured_output=True,
            max_tokens=128,
        )

    def decide(
        self,
        frame: np.ndarray,
        *,
        context: str = "",
        allowed_actions: tuple[str, ...] = DEFAULT_ACTIONS,
    ) -> dict[str, Any]:
        allowed = tuple(dict.fromkeys(("noop", *allowed_actions)))
        if not allowed or set(allowed) - SUPPORTED_ACTIONS:
            raise ValueError(
                f"allowed_actions must be a non-empty subset of {sorted(SUPPORTED_ACTIONS)}."
            )
        if not isinstance(context, str) or len(context) > MAX_CONTEXT_CHARS:
            raise ValueError(f"context must be text no longer than {MAX_CONTEXT_CHARS} characters.")
        if not isinstance(frame, np.ndarray) or frame.size == 0 or frame.ndim != 3:
            raise ValueError("frame must be a non-empty color image.")

        agent = VLMAgent(
            backend=self._backend,
            allowed_actions=list(allowed),
            system_prompt=(
                "You support local game QA. Recommend one bounded action from the allowlist. "
                "Use noop when the screen or a choice is unclear, or the next "
                "step could cause an unintended route. Do not claim that a testcase passed."
            ),
        )
        action = agent.decide(frame, context=context or None)
        fallback = agent.consecutive_fallbacks > 0
        if fallback:
            action = type(action)("noop", {})
        return {
            "api_version": API_VERSION,
            "decision_id": str(uuid.uuid4()),
            "model": self.model,
            "action": action.action,
            "params": action.params,
            "fallback": fallback,
            "frame_sha256": _frame_sha256(frame),
        }

    def health(self) -> dict[str, Any]:
        """Probe the configured OpenAI-compatible model endpoint without sending an image."""
        request = Request(
            f"{self.base_url}/models",
            headers={"Authorization": f"Bearer {self.api_key}"},
        )
        try:
            with urlopen(request, timeout=min(self.timeout, 3.0)) as response:
                payload = json.loads(response.read().decode("utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("model endpoint payload is not an object")
            model_ids = {
                str(entry.get("id", ""))
                for entry in payload.get("data", [])
                if isinstance(entry, dict)
            }
            if model_ids and self.model not in model_ids:
                return {
                    "status": "degraded",
                    "api_version": API_VERSION,
                    "model": self.model,
                    "error": "configured model is not listed by the VLM endpoint",
                }
            return {"status": "ready", "api_version": API_VERSION, "model": self.model}
        except (OSError, URLError, TimeoutError, ValueError, json.JSONDecodeError):
            return {
                "status": "degraded",
                "api_version": API_VERSION,
                "model": self.model,
                "error": "VLM endpoint is unavailable or returned invalid model metadata",
            }


def _frame_sha256(frame: np.ndarray) -> str:
    return hashlib.sha256(frame.tobytes()).hexdigest()


class DecisionRequestHandler(BaseHTTPRequestHandler):
    """Loopback HTTP transport for the local decision service."""

    server_version = "UGAFDecisionAPI/1"
    protocol_version = "HTTP/1.1"

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        if self.path != "/healthz":
            self._send_json(404, {"error": "not_found"})
            return
        service = self.server.decision_service  # type: ignore[attr-defined]
        health = getattr(service, "health", None)
        result = health() if callable(health) else {"status": "ready", "api_version": API_VERSION}
        self._send_json(200 if result.get("status") == "ready" else 503, result)

    def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        if self.path != "/v1/decision":
            self._send_json(404, {"error": "not_found"})
            return
        expected_token = self.server.api_token  # type: ignore[attr-defined]
        if expected_token and self.headers.get("Authorization") != f"Bearer {expected_token}":
            self._send_json(401, {"error": "unauthorized"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self._send_json(400, {"error": "invalid_content_length"})
            return
        if length <= 0 or length > MAX_IMAGE_BYTES * 2:
            self._send_json(
                413 if length > MAX_IMAGE_BYTES * 2 else 400, {"error": "invalid_body_size"}
            )
            return
        try:
            payload = json.loads(self.rfile.read(length))
            if not isinstance(payload, dict):
                raise ValueError("Request JSON must be an object.")
            frame = decode_frame(payload.get("image_base64"))
            actions = payload.get("allowed_actions", list(DEFAULT_ACTIONS))
            if not isinstance(actions, list) or not all(isinstance(item, str) for item in actions):
                raise ValueError("allowed_actions must be a list of strings.")
            result = self.server.decision_service.decide(  # type: ignore[attr-defined]
                frame,
                context=payload.get("context", ""),
                allowed_actions=tuple(actions),
            )
        except (json.JSONDecodeError, UnicodeDecodeError, ValueError) as exc:
            self._send_json(400, {"error": "invalid_request", "message": str(exc)})
            return
        except Exception as exc:  # The transport fails closed and does not leak request data.
            self._send_json(503, {"error": "decision_unavailable", "message": type(exc).__name__})
            return
        self._send_json(200, result)

    def log_message(self, fmt: str, *args: Any) -> None:
        # Avoid writing prompt contents, image payloads, or credentials to stderr.
        return

    def _send_json(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)


def create_server(
    service: DecisionService,
    *,
    port: int = 8765,
    api_token: str = "",
) -> ThreadingHTTPServer:
    """Create a loopback-only server; it is never exposed to the LAN by default."""
    server = ThreadingHTTPServer(("127.0.0.1", int(port)), DecisionRequestHandler)
    server.daemon_threads = True
    server.decision_service = service  # type: ignore[attr-defined]
    server.api_token = api_token  # type: ignore[attr-defined]
    return server


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run UGAF's local game-decision API.")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument(
        "--base-url",
        default=os.environ.get("VLM_BASE_URL", "http://127.0.0.1:1234/v1"),
    )
    parser.add_argument(
        "--model",
        default=os.environ.get("VLM_MODEL", "qwen/qwen2.5-vl-7b"),
    )
    parser.add_argument("--api-key", default=os.environ.get("VLM_API_KEY", "lm-studio"))
    parser.add_argument("--api-token", default=os.environ.get("UGAF_DECISION_API_TOKEN", ""))
    parser.add_argument("--timeout", type=float, default=45.0)
    args = parser.parse_args(argv)
    try:
        service = DecisionService(
            base_url=args.base_url,
            api_key=args.api_key,
            model=args.model,
            timeout=args.timeout,
        )
        server = create_server(service, port=args.port, api_token=args.api_token)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    print(f"UGAF Decision API listening on http://127.0.0.1:{args.port}")
    print("GET /healthz  POST /v1/decision")
    if args.api_token:
        print("Bearer token authentication is enabled.")
    try:
        server.serve_forever(poll_interval=0.25)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
