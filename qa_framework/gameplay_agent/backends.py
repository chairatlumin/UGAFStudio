from __future__ import annotations

import base64
import json
import os
import urllib.request
from typing import Any

import cv2
import numpy as np
from loguru import logger

from qa_framework.gameplay_agent.vlm_agent import VLMBackend


class EchoVLMBackend:
    """Deterministic fake VLM backend for testing.

    Returns the *response* string passed to its constructor, so the
    agent's decision logic can be verified end-to-end without a real model.

    Records every prompt received in ``_prompts`` for inspection.
    """

    def __init__(self, response: str) -> None:
        self._response = response
        self._prompts: list[str] = []

    # ------------------------------------------------------------------
    # VLMBackend protocol
    # ------------------------------------------------------------------

    def complete(self, prompt: str, image: np.ndarray) -> str:
        self._prompts.append(prompt)
        return self._response


class OpenAICompatBackend(VLMBackend):
    """OpenAI-compatible chat completions backend.

    Calls ``POST <base_url>/chat/completions`` with:

    - ``model`` from constructor or ``VLM_MODEL`` env var
    - ``api_key`` from constructor or ``VLM_API_KEY`` env var
    - ``messages`` built from the prompt + system instructions
    - ``image`` encoded as a base64 PNG data URL in the content

    Only stdlib ``urllib.request`` is used — no extra dependencies.
    """

    def __init__(
        self,
        *,
        base_url: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        max_tokens: int = 256,
        timeout: float = 120.0,
        structured_output: bool = False,
    ) -> None:
        self._base_url = base_url or os.environ.get("VLM_BASE_URL", "")
        self._api_key = api_key or os.environ.get("VLM_API_KEY", "")
        self._model = model or os.environ.get("VLM_MODEL", "")
        self._max_tokens = max_tokens
        self._timeout = timeout
        self._structured_output = structured_output

        if not self._base_url or not self._api_key or not self._model:
            missing = [
                n
                for n, v in [
                    ("base_url", self._base_url),
                    ("api_key", self._api_key),
                    ("model", self._model),
                ]
                if not v
            ]
            msg = f"OpenAICompatBackend missing: {', '.join(missing)}"
            logger.error(msg)
            raise ValueError(msg)

    # ------------------------------------------------------------------
    # VLMBackend protocol
    # ------------------------------------------------------------------

    @staticmethod
    def _encode_image_png(image: np.ndarray) -> str:
        """Encode a BGR numpy array as a base64 PNG data URL."""
        ok, buf = cv2.imencode(".png", image)
        if not ok:
            raise ValueError("Failed to encode image as PNG")
        b64 = base64.b64encode(buf).decode("ascii")
        return f"data:image/png;base64,{b64}"

    def _payload(self, prompt: str, image: np.ndarray) -> dict[str, Any]:
        return {
            "model": self._model,
            "messages": [
                {
                    "role": "system",
                    "content": "You are a game QA vision assistant. Return only the requested JSON.",
                },
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": self._encode_image_png(image)}},
                    ],
                },
            ],
            "temperature": 0.0,
            "max_tokens": self._max_tokens,
        }

    def _post_payload(self, payload: dict[str, Any]) -> str:
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url=f"{self._base_url}/chat/completions",
            data=body,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self._api_key}",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                result: dict[str, Any] = json.loads(resp.read().decode("utf-8"))
                message: dict[str, Any] = result["choices"][0]["message"]
                content: str = message.get("content") or ""
                if not content.strip():
                    reasoning: str = message.get("reasoning_content") or ""
                    if reasoning.strip():
                        logger.warning("Empty content, falling back to reasoning_content")
                        return reasoning
                    msg = "OpenAICompatBackend: model returned empty content and reasoning_content"
                    logger.error(msg)
                    raise ValueError(msg)
                return content
        except Exception as exc:
            logger.error("OpenAICompatBackend error: {}", exc)
            raise

    def complete_json(
        self,
        prompt: str,
        image: np.ndarray,
        *,
        schema_name: str,
        schema: dict[str, Any],
    ) -> str:
        """Request a caller-defined strict JSON Schema vision response."""
        payload = self._payload(prompt, image)
        payload["response_format"] = {
            "type": "json_schema",
            "json_schema": {"name": schema_name, "strict": True, "schema": schema},
        }
        return self._post_payload(payload)

    def complete(self, prompt: str, image: np.ndarray) -> str:
        payload = self._payload(prompt, image)
        if self._structured_output:
            # Syntax is constrained here; the agent still validates the action
            # allowlist, required fields and frame bounds before input dispatch.
            action_variants = []
            parameter_schemas: dict[str, dict[str, Any]] = {
                "noop": {"type": "object", "properties": {}, "additionalProperties": False},
                "click": {
                    "type": "object",
                    "properties": {
                        "button": {"type": "string", "enum": ["left", "right", "middle"]},
                        "x": {"type": "integer"},
                        "y": {"type": "integer"},
                    },
                    "required": ["x", "y"],
                    "additionalProperties": False,
                },
                "mouse_move": {
                    "type": "object",
                    "properties": {"x": {"type": "integer"}, "y": {"type": "integer"}},
                    "required": ["x", "y"],
                    "additionalProperties": False,
                },
                "key_press": {"type": "object", "properties": {"key": {"type": "string"}}, "required": ["key"], "additionalProperties": False},
                "key_release": {"type": "object", "properties": {"key": {"type": "string"}}, "required": ["key"], "additionalProperties": False},
                "key_hold": {"type": "object", "properties": {"key": {"type": "string"}}, "required": ["key"], "additionalProperties": False},
                "type_text": {
                    "type": "object",
                    "properties": {"text": {"type": "string", "minLength": 1, "maxLength": 32}},
                    "required": ["text"],
                    "additionalProperties": False,
                },
            }
            for action in ("noop", "click", "mouse_move", "key_press", "key_release", "key_hold", "type_text"):
                if action in {"noop", "click", "mouse_move", "key_press", "key_release", "key_hold", "type_text"}:
                    action_variants.append({
                        "type": "object",
                        "properties": {
                            "action": {"type": "string", "enum": [action]},
                            "params": parameter_schemas[action],
                        },
                        "required": ["action", "params"],
                        "additionalProperties": False,
                    })
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": "gameplay_action",
                    "strict": True,
                    "schema": {"anyOf": action_variants},
                },
            }

        return self._post_payload(payload)
