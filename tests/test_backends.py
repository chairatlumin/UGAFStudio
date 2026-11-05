from __future__ import annotations

import json
from unittest.mock import patch

import numpy as np
import pytest

from qa_framework.gameplay_agent.backends import (
    EchoVLMBackend,
    OpenAICompatBackend,
)


class _FakeResponse:
    """Minimal stand-in for urllib's HTTPResponse (context manager)."""

    def __init__(self, payload: dict) -> None:
        self._payload = json.dumps(payload).encode("utf-8")

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    def read(self) -> bytes:
        return self._payload


def _frame() -> np.ndarray:
    return np.zeros((8, 8, 3), dtype=np.uint8)


def test_echo_backend_returns_response_and_records_prompt() -> None:
    """EchoVLMBackend is the deterministic fake the agent tests rely on."""
    backend = EchoVLMBackend(response='{"action": "click"}')
    out = backend.complete("the-prompt", _frame())
    assert out == '{"action": "click"}'
    assert backend._prompts == ["the-prompt"]


def test_openai_backend_returns_content() -> None:
    """Nominal path: content field is returned verbatim."""
    payload = {"choices": [{"message": {"content": '{"action": "key_press"}'}}]}
    with patch("urllib.request.urlopen", return_value=_FakeResponse(payload)):
        backend = OpenAICompatBackend(base_url="http://x/v1", api_key="k", model="m", timeout=5)
        assert backend.complete("p", _frame()) == '{"action": "key_press"}'


def test_openai_backend_falls_back_to_reasoning_content() -> None:
    """Reasoning models (e.g. gemma thinking) leave content empty and put the
    answer in reasoning_content. The backend must fall back to it."""
    payload = {
        "choices": [{"message": {"content": "", "reasoning_content": '{"action": "click"}'}}]
    }
    with patch("urllib.request.urlopen", return_value=_FakeResponse(payload)):
        backend = OpenAICompatBackend(base_url="http://x/v1", api_key="k", model="m", timeout=5)
        assert backend.complete("p", _frame()) == '{"action": "click"}'


def test_openai_backend_empty_both_raises() -> None:
    """When both content and reasoning_content are empty, the model produced
    nothing usable -> raise so the agent can fall back."""
    payload = {"choices": [{"message": {"content": "", "reasoning_content": ""}}]}
    with patch("urllib.request.urlopen", return_value=_FakeResponse(payload)):
        backend = OpenAICompatBackend(base_url="http://x/v1", api_key="k", model="m", timeout=5)
        with pytest.raises(Exception):
            backend.complete("p", _frame())


def test_openai_backend_missing_config_raises() -> None:
    """Missing base_url / api_key / model must raise at construction."""
    with pytest.raises(ValueError):
        OpenAICompatBackend(base_url="", api_key="k", model="m")
    with pytest.raises(ValueError):
        OpenAICompatBackend(base_url="http://x/v1", api_key="", model="m")
    with pytest.raises(ValueError):
        OpenAICompatBackend(base_url="http://x/v1", api_key="k", model="")


def test_openai_backend_encodes_image_png() -> None:
    """The frame is encoded as a base64 PNG data URL in the request body."""
    captured: dict = {}

    def _fake_urlopen(req: object, timeout: float = 0) -> _FakeResponse:  # noqa: ANN001
        captured["body"] = json.loads(req.data.decode("utf-8"))  # type: ignore[attr-defined]
        return _FakeResponse({"choices": [{"message": {"content": "{}"}}]})

    with patch("urllib.request.urlopen", _fake_urlopen):
        backend = OpenAICompatBackend(base_url="http://x/v1", api_key="k", model="m", timeout=5)
        backend.complete("p", _frame())

    content = captured["body"]["messages"][1]["content"]
    assert any(
        item.get("type") == "image_url"
        and item["image_url"]["url"].startswith("data:image/png;base64,")
        for item in content
    )


def test_openai_backend_requests_structured_json_schema_when_enabled() -> None:
    captured: dict = {}

    def _fake_urlopen(req: object, timeout: float = 0) -> _FakeResponse:  # noqa: ANN001
        captured["body"] = json.loads(req.data.decode("utf-8"))  # type: ignore[attr-defined]
        return _FakeResponse({"choices": [{"message": {"content": '{"action":"noop","params":{}}'}}]})

    with patch("urllib.request.urlopen", _fake_urlopen):
        backend = OpenAICompatBackend(
            base_url="http://x/v1", api_key="k", model="m", timeout=5,
            structured_output=True,
        )
        backend.complete("p", _frame())

    fmt = captured["body"]["response_format"]
    assert fmt["type"] == "json_schema"
    schema = fmt["json_schema"]["schema"]
    assert "anyOf" in schema
    click_schema = next(v for v in schema["anyOf"] if v["properties"]["action"]["enum"] == ["click"])
    assert click_schema["properties"]["params"]["required"] == ["x", "y"]
    assert "coordinate" not in click_schema["properties"]["params"]["properties"]


def test_openai_backend_supports_caller_defined_structured_vision_schema() -> None:
    captured: dict = {}

    def _fake_urlopen(req: object, timeout: float = 0) -> _FakeResponse:  # noqa: ANN001
        captured["body"] = json.loads(req.data.decode("utf-8"))  # type: ignore[attr-defined]
        return _FakeResponse({"choices": [{"message": {"content": '{"choices": []}'}}]})

    schema = {
        "type": "object",
        "properties": {"choices": {"type": "array", "items": {"type": "string", "enum": ["Go Left"]}}},
        "required": ["choices"],
        "additionalProperties": False,
    }
    with patch("urllib.request.urlopen", _fake_urlopen):
        backend = OpenAICompatBackend(base_url="http://x/v1", api_key="k", model="m")
        assert backend.complete_json("detect", _frame(), schema_name="visible_story_choices", schema=schema) == '{"choices": []}'

    fmt = captured["body"]["response_format"]
    assert fmt["type"] == "json_schema"
    assert fmt["json_schema"]["name"] == "visible_story_choices"
    assert fmt["json_schema"]["schema"] == schema


def test_openai_backend_omits_structured_json_by_default() -> None:
    captured: dict = {}

    def _fake_urlopen(req: object, timeout: float = 0) -> _FakeResponse:  # noqa: ANN001
        captured["body"] = json.loads(req.data.decode("utf-8"))  # type: ignore[attr-defined]
        return _FakeResponse({"choices": [{"message": {"content": "{}"}}]})

    with patch("urllib.request.urlopen", _fake_urlopen):
        OpenAICompatBackend(base_url="http://x/v1", api_key="k", model="m").complete("p", _frame())

    assert "response_format" not in captured["body"]
