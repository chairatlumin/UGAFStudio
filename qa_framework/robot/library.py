"""Robot Framework keywords backed by UGAF's capture, input, and vision services."""

from __future__ import annotations

import base64
import copy
import ctypes
import hashlib
import json
import os
import re
import time
import urllib.error
import urllib.request
from ctypes import wintypes
from pathlib import Path
from typing import Any, Callable

import cv2
import numpy as np

from app.capture.capture_service import CaptureService
from app.input.keyboard_service import KeyboardService
from app.input.mouse_service import MouseService
from app.utils.file import unique_path
from app.vision.color_detector import ColorDetector
from app.vision.ocr import OCREngine
from qa_framework.gameplay_agent.vlm_agent import _validated_action


class UGAFKeywords:
    """Keyword library for screen-based game QA.

    Input is disabled until ``Enable Game Input`` is called by a suite. This
    makes a mistakenly selected suite safe to inspect without sending clicks
    or keystrokes to whichever application currently has focus.
    """

    ROBOT_LIBRARY_SCOPE = "SUITE"
    ROBOT_LIBRARY_VERSION = "0.1.0"
    DECISION_MAX_AGE_SECONDS = 3.0

    def __init__(
        self,
        output_dir: str | Path | None = None,
        capture: CaptureService | None = None,
        mouse: MouseService | None = None,
        keyboard: KeyboardService | None = None,
        ocr: OCREngine | None = None,
        color_detector: ColorDetector | None = None,
        focus_checker: Callable[[str], bool] | None = None,
    ) -> None:
        configured_output = (
            output_dir or os.environ.get("UGAF_ROBOT_OUTPUT_DIR") or "screenshots/robot"
        )
        self.output_dir = Path(configured_output).expanduser().resolve()
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._capture = capture or CaptureService()
        self._mouse = mouse or MouseService()
        self._keyboard = keyboard or KeyboardService()
        self._ocr = ocr or OCREngine()
        self._color = color_detector or ColorDetector()
        self._focus_checker = focus_checker or _foreground_window_matches
        self._input_enabled = False
        self._expected_window_title = ""
        self._last_frame: np.ndarray | None = None
        self._last_decision: dict[str, Any] | None = None
        self._last_decision_at: float | None = None
        self._decision_api_url = "http://127.0.0.1:8765"
        self._decision_api_token = ""
        self.set_decision_api_endpoint(
            os.environ.get("UGAF_DECISION_API_URL", self._decision_api_url),
            os.environ.get("UGAF_DECISION_API_TOKEN", ""),
        )

    def enable_game_input(self, expected_window_title: str) -> None:
        """Enable input only while the explicitly named game window is foreground."""
        expected = str(expected_window_title).strip()
        if not expected:
            raise ValueError("expected_window_title is required to enable game input.")
        if not self._focus_checker(expected):
            raise RuntimeError(
                f"Foreground window does not match expected game title {expected!r}."
            )
        self._expected_window_title = expected
        self._input_enabled = True

    def capture_screen(self) -> np.ndarray:
        """Capture the selected display and retain it for subsequent assertions."""
        self._last_frame = self._capture.capture()
        self._last_decision = None
        self._last_decision_at = None
        if self._last_frame.size == 0:
            raise AssertionError("Screen capture returned an empty frame.")
        return self._last_frame

    def save_screenshot(self, name: str = "screen") -> str:
        """Capture the screen and save a PNG in the configured output directory."""
        return self._save_frame(self.capture_screen(), name)

    def use_monitor(self, monitor_index: int) -> None:
        """Select a monitor (0 is the virtual desktop; 1 is the primary display)."""
        monitors = self._capture.all_monitors()
        index = int(monitor_index)
        if index < 0 or index >= len(monitors):
            raise ValueError(
                f"Monitor index {index} is invalid; available: 0..{len(monitors) - 1}."
            )
        self._capture.set_monitor(index)

    def click_at(self, x: int, y: int, button: str = "left") -> None:
        """Click at absolute screen coordinates after input has been enabled."""
        self._require_input()
        button_name = str(button).casefold()
        if button_name not in {"left", "right", "middle"}:
            raise ValueError("button must be left, right, or middle.")
        self._mouse.click(int(x), int(y), button=button_name)

    def press_key(self, key: str) -> None:
        """Press one keyboard key after input has been enabled."""
        self._require_input()
        normalized = str(key).strip()
        if not normalized:
            raise ValueError("key cannot be empty.")
        self._keyboard.press(normalized)

    def type_text(self, text: str, interval: float = 0.0) -> None:
        """Type text after input has been enabled."""
        self._require_input()
        delay = float(interval)
        if delay < 0:
            raise ValueError("interval cannot be negative.")
        self._keyboard.write(str(text), interval=delay)

    def wait_for_text(
        self,
        text: str,
        timeout: float = 10.0,
        interval: float = 0.5,
        language: str = "eng",
    ) -> str:
        """Wait until OCR finds text and return the captured screenshot path."""
        expected = str(text).strip()
        if not expected:
            raise ValueError("text cannot be empty.")
        timeout_value = float(timeout)
        interval_value = float(interval)
        if timeout_value < 0 or interval_value <= 0:
            raise ValueError("timeout must be non-negative and interval must be positive.")
        if not self._ocr.available():
            raise RuntimeError(
                "OCR is unavailable. Install Tesseract and configure its language data."
            )

        deadline = time.monotonic() + timeout_value
        latest_text = ""
        while True:
            frame = self.capture_screen()
            latest_text = self._ocr.read(frame, lang=str(language))
            if expected.casefold() in latest_text.casefold():
                return self.save_screenshot("text_found")
            if time.monotonic() >= deadline:
                raise AssertionError(
                    f"Timed out after {timeout_value:g}s waiting for {expected!r}. "
                    f"Last OCR text: {latest_text[:500]!r}"
                )
            time.sleep(min(interval_value, max(0.0, deadline - time.monotonic())))

    def text_should_be_visible(self, text: str, language: str = "eng") -> None:
        """Assert that OCR on the current screen contains the requested text."""
        frame = self._current_frame()
        if not self._ocr.available():
            raise RuntimeError(
                "OCR is unavailable. Install Tesseract and configure its language data."
            )
        actual = self._ocr.read(frame, lang=str(language))
        if str(text).casefold() not in actual.casefold():
            raise AssertionError(f"Expected screen text {text!r}; OCR recognized {actual[:500]!r}.")

    def frame_should_not_be_black(
        self,
        brightness_threshold: int = 8,
        minimum_visible_ratio: float = 0.02,
    ) -> None:
        """Assert that the current screen contains enough visible pixels."""
        frame = self._current_frame()
        threshold = int(brightness_threshold)
        minimum = float(minimum_visible_ratio)
        if not 0 <= threshold <= 255 or not 0.0 <= minimum <= 1.0:
            raise ValueError("threshold must be 0..255 and visible ratio must be 0..1.")
        color_frame = frame[:, :, :3] if frame.ndim == 3 and frame.shape[2] == 4 else frame
        visible = (
            np.any(color_frame > threshold, axis=2)
            if color_frame.ndim == 3
            else color_frame > threshold
        )
        ratio = float(np.count_nonzero(visible) / visible.size)
        if ratio < minimum:
            raise AssertionError(
                f"Screen appears black: visible ratio {ratio:.4f} < {minimum:.4f}."
            )

    def color_should_be_present(
        self,
        blue: int,
        green: int,
        red: int,
        tolerance: int = 30,
    ) -> None:
        """Assert a BGR color is present on the current screen."""
        color = (int(blue), int(green), int(red))
        if any(value < 0 or value > 255 for value in color):
            raise ValueError("BGR color channels must be between 0 and 255.")
        result = self._color.detect(self._current_frame(), color, tolerance=int(tolerance))
        if result is None:
            raise AssertionError(f"BGR color {color} was not found within tolerance {tolerance}.")

    def set_decision_api_endpoint(self, url: str, token: str = "") -> None:
        """Configure the local Decision API endpoint and optional bearer token."""
        from urllib.parse import urlparse

        parsed = urlparse(str(url).strip())
        if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
            raise ValueError("Decision API must use HTTP on loopback to keep game frames local.")
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("Decision API URL cannot contain credentials, query, or fragment.")
        if parsed.path not in {"", "/"}:
            raise ValueError("Decision API URL must be an origin without a path.")
        self._decision_api_url = str(url).strip().rstrip("/")
        self._decision_api_token = str(token)

    def decision_api_should_be_ready(self, expected_model: str = "") -> dict[str, Any]:
        """Assert that the configured local Decision API and its VLM are ready."""
        headers: dict[str, str] = {}
        if self._decision_api_token:
            headers["Authorization"] = f"Bearer {self._decision_api_token}"
        request = urllib.request.Request(
            f"{self._decision_api_url}/healthz", headers=headers, method="GET"
        )
        try:
            with urllib.request.urlopen(request, timeout=4.0) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise AssertionError(f"Decision API health check failed: {exc}") from exc
        if not isinstance(payload, dict) or payload.get("status") != "ready":
            raise AssertionError(f"Decision API is not ready: {payload!r}")
        if payload.get("api_version") != "1" or not payload.get("model"):
            raise AssertionError(f"Decision API health response is incomplete: {payload!r}")
        expected = str(expected_model).strip()
        if expected and payload.get("model") != expected:
            raise AssertionError(
                f"Decision API model mismatch: expected {expected!r}, "
                f"received {payload.get('model')!r}."
            )
        return payload

    def ask_next_action(
        self,
        context: str = "",
        allowed_actions: str = "noop,click,key_press",
        timeout: float = 50.0,
    ) -> dict[str, Any]:
        """Ask the local VLM Decision API for one bounded action on the current frame."""
        actions = tuple(
            dict.fromkeys(
                (
                    "noop",
                    *(part.strip() for part in str(allowed_actions).split(",") if part.strip()),
                )
            )
        )
        supported = {"noop", "click", "key_press"}
        if not actions or set(actions) - supported:
            raise ValueError(f"allowed_actions must be selected from {sorted(supported)}.")
        frame = self.capture_screen()
        encoded_ok, encoded = cv2.imencode(".png", frame)
        if not encoded_ok:
            raise RuntimeError("Could not encode the captured frame for the Decision API.")
        encoded_bytes = encoded.tobytes()
        payload = json.dumps(
            {
                "image_base64": base64.b64encode(encoded_bytes).decode("ascii"),
                "context": str(context),
                "allowed_actions": list(actions),
            }
        ).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if self._decision_api_token:
            headers["Authorization"] = f"Bearer {self._decision_api_token}"
        request = urllib.request.Request(
            f"{self._decision_api_url}/v1/decision", data=payload, headers=headers, method="POST"
        )
        try:
            with urllib.request.urlopen(request, timeout=float(timeout)) as response:
                result = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"Decision API request failed: {exc}") from exc
        if not isinstance(result, dict) or result.get("api_version") != "1":
            raise RuntimeError("Decision API returned an invalid response schema.")
        if result.get("fallback") is not False:
            result.update(action="noop", params={}, fallback=True)
        if result.get("action") not in actions or not isinstance(result.get("params"), dict):
            raise RuntimeError("Decision API returned an action outside the requested allowlist.")
        decoded = cv2.imdecode(np.frombuffer(encoded_bytes, dtype=np.uint8), cv2.IMREAD_COLOR)
        expected_hash = hashlib.sha256(decoded.tobytes()).hexdigest()
        if result.get("frame_sha256") != expected_hash:
            raise RuntimeError("Decision API response does not match the submitted frame.")
        result["evidence_path"] = self._save_frame(frame, "decision_frame")
        result["allowed_actions"] = list(actions)
        self._last_decision = copy.deepcopy(result)
        self._last_decision_at = time.monotonic()
        return result

    def apply_decision(self, decision: dict[str, Any] | None = None) -> str:
        """Apply the most recent API decision after explicit input enablement and revalidation."""
        self._require_input()
        current = decision if decision is not None else self._last_decision
        if not isinstance(current, dict) or self._last_decision is None:
            raise RuntimeError("No fresh Decision API result is available to apply.")
        if self._last_decision_at is None or (
            time.monotonic() - self._last_decision_at > self.DECISION_MAX_AGE_SECONDS
        ):
            self._last_decision = None
            self._last_decision_at = None
            raise RuntimeError(
                "Decision expired before it could be applied; request a new frame decision."
            )
        if current.get("decision_id") != self._last_decision.get("decision_id"):
            raise RuntimeError("Decision is stale or was not returned by this library instance.")
        for field in ("action", "params", "fallback", "frame_sha256", "allowed_actions"):
            if current.get(field) != self._last_decision.get(field):
                raise RuntimeError(f"Decision field {field!r} was modified after it was received.")
        if current.get("fallback") or current.get("action") == "noop":
            return "noop"
        frame = self._last_frame
        if frame is None:
            raise RuntimeError("Decision frame is no longer available.")
        actions = current.get("allowed_actions", [])
        if not isinstance(actions, list) or set(actions) - {"noop", "click", "key_press"}:
            raise RuntimeError("Decision action allowlist is invalid.")
        action = _validated_action(
            {"action": current.get("action"), "params": current.get("params")}, actions, frame
        )
        if action is None:
            raise RuntimeError("Decision failed local action/frame-bound validation.")
        if action.action == "click":
            monitor = self._capture.current_monitor()
            self._mouse.click(
                int(action.params["x"]) + int(monitor.left),
                int(action.params["y"]) + int(monitor.top),
                button=str(action.params.get("button", "left")),
            )
        elif action.action == "key_press":
            self._keyboard.press(str(action.params["key"]))
        else:
            return "noop"
        self._last_decision = None
        self._last_decision_at = None
        return action.action

    def close(self) -> None:
        """Release the underlying MSS capture handle when Robot closes the suite."""
        close = getattr(self._capture, "close", None)
        if callable(close):
            close()

    def _current_frame(self) -> np.ndarray:
        return self._last_frame if self._last_frame is not None else self.capture_screen()

    def _save_frame(self, frame: np.ndarray, name: str) -> str:
        safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("._") or "screen"
        path = unique_path(self.output_dir, safe_name, "png")
        if not cv2.imwrite(str(path), frame):
            raise OSError(f"Could not save screenshot: {path}")
        return str(path)

    def _require_input(self) -> None:
        if not self._input_enabled:
            raise RuntimeError(
                "Game input is disabled. Confirm the target window, then call "
                "'Enable Game Input' with its title."
            )
        if not self._focus_checker(self._expected_window_title):
            self._input_enabled = False
            raise RuntimeError(
                f"Input stopped because foreground no longer matches "
                f"{self._expected_window_title!r}."
            )


def _foreground_window_matches(expected_title: str) -> bool:
    """Return true only when a Windows foreground title contains expected text."""
    if os.name != "nt":
        return False
    user32 = ctypes.windll.user32
    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.GetWindowTextW.argtypes = (wintypes.HWND, wintypes.LPWSTR, ctypes.c_int)
    user32.GetWindowTextW.restype = ctypes.c_int
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return False
    title = ctypes.create_unicode_buffer(512)
    user32.GetWindowTextW(hwnd, title, len(title))
    return expected_title.casefold() in title.value.casefold()
