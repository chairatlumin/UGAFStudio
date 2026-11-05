from __future__ import annotations

import base64
import json
import threading
import time
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import cv2
import numpy as np
import pytest
from PIL import Image

from qa_framework.robot.decision_api import DecisionService, create_server, decode_frame
from qa_framework.robot.library import UGAFKeywords


class FakeBackend:
    def __init__(self, response: str) -> None:
        self.response = response

    def complete(self, prompt: str, image: np.ndarray) -> str:
        assert "noop" in prompt
        assert image.ndim == 3
        return self.response


def encoded_image() -> str:
    image = np.full((12, 18, 3), 180, dtype=np.uint8)
    ok, buffer = cv2.imencode(".png", image)
    assert ok
    return base64.b64encode(buffer.tobytes()).decode("ascii")


def test_decision_service_returns_validated_action_and_frame_hash() -> None:
    frame = decode_frame(encoded_image())
    service = DecisionService(
        model="test-model",
        backend=FakeBackend('{"action":"click","params":{"x":4,"y":5}}'),
    )

    result = service.decide(frame, context="title screen")

    assert result["action"] == "click"
    assert result["params"] == {"x": 4, "y": 5, "button": "left"}
    assert result["fallback"] is False
    assert len(result["frame_sha256"]) == 64


def test_decision_service_falls_back_to_noop_on_unsafe_model_action() -> None:
    frame = decode_frame(encoded_image())
    service = DecisionService(
        model="test-model",
        backend=FakeBackend('{"action":"type_text","params":{"text":"unsafe"}}'),
    )

    result = service.decide(frame)

    assert result["action"] == "noop"
    assert result["params"] == {}
    assert result["fallback"] is True


def test_decode_frame_rejects_invalid_base64() -> None:
    with pytest.raises(ValueError, match="valid base64"):
        decode_frame("%%%not-image%%")


def test_decode_frame_rejects_oversized_dimensions_before_pixel_decode() -> None:
    import io

    stream = io.BytesIO()
    Image.new("RGB", (3841, 1)).save(stream, format="PNG")
    with pytest.raises(ValueError, match="dimensions"):
        decode_frame(base64.b64encode(stream.getvalue()).decode("ascii"))


class EchoDecisionService:
    def decide(
        self,
        frame: np.ndarray,
        *,
        context: str = "",
        allowed_actions: tuple[str, ...] = (),
    ) -> dict[str, Any]:
        return {
            "api_version": "1",
            "action": "noop",
            "params": {},
            "fallback": False,
            "context_seen": context,
            "actions_seen": list(allowed_actions),
            "width": frame.shape[1],
        }


def test_loopback_http_api_health_and_decision_endpoints() -> None:
    server: ThreadingHTTPServer = create_server(EchoDecisionService(), port=0, api_token="secret")  # type: ignore[arg-type]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        with urllib.request.urlopen(f"{base_url}/healthz", timeout=2) as response:
            assert json.loads(response.read())["status"] == "ready"

        body = json.dumps(
            {
                "image_base64": encoded_image(),
                "context": "test context",
                "allowed_actions": ["noop"],
            }
        ).encode()
        request = urllib.request.Request(
            f"{base_url}/v1/decision",
            data=body,
            headers={"Content-Type": "application/json", "Authorization": "Bearer secret"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=2) as response:
            result = json.loads(response.read())
        assert result["action"] == "noop"
        assert result["context_seen"] == "test context"
        assert result["width"] == 18

        unauthorized = urllib.request.Request(
            f"{base_url}/v1/decision",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with pytest.raises(urllib.error.HTTPError) as error:
            urllib.request.urlopen(unauthorized, timeout=2)
        assert error.value.code == 401
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_robot_decision_keyword_revalidates_and_requires_input_enable(tmp_path: Path) -> None:
    service = DecisionService(
        model="test-model",
        backend=FakeBackend('{"action":"click","params":{"x":4,"y":5}}'),
    )
    server = create_server(service, port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    mouse = SimpleNamespace(clicked=None)

    def click(x: int, y: int, button: str = "left") -> None:
        mouse.clicked = (x, y, button)

    class FakeMouse:
        def click(self, x: int, y: int, button: str = "left") -> None:
            click(x, y, button)

    class FakeCapture:
        def __init__(self) -> None:
            self.frame = np.full((12, 18, 4), 180, dtype=np.uint8)
            self.frame[:, :, 3] = 255

        def capture(self) -> np.ndarray:
            return self.frame

        def current_monitor(self) -> SimpleNamespace:
            return SimpleNamespace(left=0, top=0)

    library = UGAFKeywords(
        output_dir=tmp_path,
        capture=FakeCapture(),  # type: ignore[arg-type]
        mouse=FakeMouse(),  # type: ignore[arg-type]
        keyboard=SimpleNamespace(press=lambda key: None),  # type: ignore[arg-type]
        focus_checker=lambda title: True,
    )
    library.set_decision_api_endpoint(f"http://127.0.0.1:{server.server_address[1]}")
    try:
        decision = library.ask_next_action("A visible story choice is on screen.")
        assert decision["action"] == "click"
        assert Path(decision["evidence_path"]).is_file()
        with pytest.raises(RuntimeError, match="input is disabled"):
            library.apply_decision(decision)

        library.enable_game_input("Test Game")
        assert library.apply_decision(decision) == "click"
        assert mouse.clicked == (4, 5, "left")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_robot_rejects_mutated_decision_before_input(tmp_path: Path) -> None:
    service = DecisionService(
        model="test-model",
        backend=FakeBackend('{"action":"click","params":{"x":4,"y":5}}'),
    )
    server = create_server(service, port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    library = UGAFKeywords(
        output_dir=tmp_path,
        capture=SimpleNamespace(capture=lambda: np.zeros((12, 18, 4), dtype=np.uint8)),
        mouse=SimpleNamespace(click=lambda *args, **kwargs: None),
        keyboard=SimpleNamespace(press=lambda key: None),
        focus_checker=lambda title: True,
    )  # type: ignore[arg-type]
    library.set_decision_api_endpoint(f"http://127.0.0.1:{server.server_address[1]}")
    try:
        decision = library.ask_next_action()
        decision["params"]["x"] = 6
        library.enable_game_input("Test Game")
        with pytest.raises(RuntimeError, match="modified"):
            library.apply_decision(decision)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_robot_rejects_expired_decision_before_input(tmp_path: Path) -> None:
    mouse = SimpleNamespace(clicked=None)
    library = UGAFKeywords(
        output_dir=tmp_path,
        capture=SimpleNamespace(
            capture=lambda: np.full((12, 18, 4), 180, dtype=np.uint8),
            current_monitor=lambda: SimpleNamespace(left=0, top=0),
        ),
        mouse=SimpleNamespace(
            click=lambda x, y, button="left": setattr(mouse, "clicked", (x, y, button))
        ),
        keyboard=SimpleNamespace(press=lambda key: None),
        focus_checker=lambda title: True,
    )  # type: ignore[arg-type]
    library.enable_game_input("Test Game")
    decision = {
        "decision_id": "expired",
        "action": "click",
        "params": {"x": 4, "y": 5},
        "fallback": False,
        "frame_sha256": "unused-in-expired-case",
        "allowed_actions": ["noop", "click"],
    }
    library._last_decision = decision.copy()
    library._last_decision_at = (
        time.monotonic() - library.DECISION_MAX_AGE_SECONDS - 1
    )

    with pytest.raises(RuntimeError, match="Decision expired"):
        library.apply_decision(decision)

    assert mouse.clicked is None


def test_robot_decision_endpoint_rejects_remote_hosts(tmp_path: Path) -> None:
    library = UGAFKeywords(
        output_dir=tmp_path,
        capture=SimpleNamespace(capture=lambda: np.zeros((1, 1, 4), dtype=np.uint8)),
        mouse=SimpleNamespace(click=lambda *args, **kwargs: None),
        keyboard=SimpleNamespace(press=lambda key: None),
    )  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="loopback"):
        library.set_decision_api_endpoint("https://example.invalid")


def test_robot_decision_api_readiness_keyword_checks_model(tmp_path: Path) -> None:
    class ReadyService:
        def health(self) -> dict[str, str]:
            return {"status": "ready", "api_version": "1", "model": "test-model"}

    server = create_server(ReadyService(), port=0)  # type: ignore[arg-type]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    library = UGAFKeywords(
        output_dir=tmp_path,
        capture=SimpleNamespace(capture=lambda: np.zeros((1, 1, 4), dtype=np.uint8)),
        mouse=SimpleNamespace(click=lambda *args, **kwargs: None),
        keyboard=SimpleNamespace(press=lambda key: None),
    )  # type: ignore[arg-type]
    library.set_decision_api_endpoint(f"http://127.0.0.1:{server.server_address[1]}")
    try:
        assert library.decision_api_should_be_ready("test-model")["status"] == "ready"
        with pytest.raises(AssertionError, match="model mismatch"):
            library.decision_api_should_be_ready("other-model")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
