"""Real-game loop: capture game window, feed frames
to VLMAgent, dispatch decided actions via REAL KeyboardService/MouseService,
with F12 kill-switch.  Game-agnostic via profiles in game_profiles.json.
"""

from __future__ import annotations

import argparse
import ctypes
import ctypes.wintypes as wt
import json
import math
import re
import sqlite3
import sys
import time
from collections import deque
from pathlib import Path
from typing import Any, cast

import cv2
import numpy as np
from loguru import logger

from qa_framework.gameplay_agent.actions import Action, ActionExecutor
from qa_framework.gameplay_agent.backends import OpenAICompatBackend
from qa_framework.gameplay_agent.moa import ALLOWED_BUTTONS, ALLOWED_KEYS, MOAAgent
from qa_framework.gameplay_agent.reward import FrameDiffReward
from qa_framework.gameplay_agent.skill_cache import SkillCache, _visual_hash, signature
from qa_framework.gameplay_agent.state_oracle import ProfileStateOracle
from qa_framework.gameplay_agent.vlm_agent import VLMAgent
from scripts.session_report import build_report as _build_session_report

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32
try:  # ponytail: physical px so PrintWindow rect and SetCursorPos clicks agree.
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except (OSError, AttributeError):
    pass
VK_F12 = 0x7B
PW_RENDERFULLCONTENT = 2
PROFILE_PATH = Path(__file__).resolve().parent / "game_profiles.json"
if getattr(sys, "_MEIPASS", None):  # ponytail: frozen modules have no real __file__ dir
    _bundled = Path(sys._MEIPASS) / "scripts" / "game_profiles.json"
    if _bundled.is_file():
        PROFILE_PATH = _bundled

# ---------------------------------------------------------------------------
# BITMAPINFOHEADER for GetDIBits
# ---------------------------------------------------------------------------


class _BMIH(ctypes.Structure):
    _fields_ = [
        ("biSize", ctypes.c_uint32),
        ("biWidth", ctypes.c_int32),
        ("biHeight", ctypes.c_int32),
        ("biPlanes", ctypes.c_uint16),
        ("biBitCount", ctypes.c_uint16),
        ("biCompression", ctypes.c_uint32),
        ("biSizeImage", ctypes.c_uint32),
        ("biXPelsPerMeter", ctypes.c_int32),
        ("biYPelsPerMeter", ctypes.c_int32),
        ("biClrUsed", ctypes.c_uint32),
        ("biClrImportant", ctypes.c_uint32),
    ]


# ---------------------------------------------------------------------------
# Window helpers
# ---------------------------------------------------------------------------


def find_game_hwnd(title_part: str = "Agent Veil") -> list[tuple[int, str]]:
    """Return visible windows whose title contains *title_part*."""
    needle = title_part.lower()
    found: list[tuple[int, str]] = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)
    def _cb(h: wt.HWND, _: wt.LPARAM) -> bool:
        buf = ctypes.create_string_buffer(256)
        user32.GetWindowTextA(h, buf, 256)
        name = buf.value.decode("utf-8", "ignore")
        if needle in name.lower():
            found.append((int(h), name))
        return True

    user32.EnumWindows(_cb, 0)
    return [(h, n) for h, n in found if user32.IsWindowVisible(h)]


def get_window_rect(hwnd: int) -> tuple[int, int, int, int]:
    """Return (left, top, right, bottom) for *hwnd*."""
    r = wt.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(r))
    return r.left, r.top, r.right, r.bottom


def focus_game_window(hwnd: int) -> bool:
    """Bring the game to the foreground without clicking the video surface."""
    # ponytail: AttachThreadInput so SetForegroundWindow succeeds on Unreal
    # fullscreen/elevated windows that ignore synthetic input when unfocused.
    try:
        game_tid = user32.GetWindowThreadProcessId(hwnd, None)
        cur_tid = ctypes.windll.kernel32.GetCurrentThreadId()
        user32.AttachThreadInput(cur_tid, game_tid, True)
        user32.ShowWindow(hwnd, 9)  # SW_RESTORE
        user32.BringWindowToTop(hwnd)
        user32.SetForegroundWindow(hwnd)
        user32.AttachThreadInput(cur_tid, game_tid, False)
    except (OSError, ctypes.ArgumentError):
        user32.ShowWindow(hwnd, 9)
        user32.BringWindowToTop(hwnd)
        user32.SetForegroundWindow(hwnd)
    time.sleep(0.15)
    return int(user32.GetForegroundWindow()) == hwnd


def grab_frame(hwnd: int) -> np.ndarray:
    """Capture the game client, preferring the live desktop for a foreground window.

    Unreal's hardware-rendered video can leave ``PrintWindow`` returning an old
    frame even while the game has advanced. A foreground window is therefore
    sampled from the physical desktop first; ``PrintWindow`` remains the
    fallback for occluded/background windows. Returns a BGR numpy array.
    """
    left, top, right, bottom = get_window_rect(hwnd)
    w, h = right - left, bottom - top

    if int(user32.GetForegroundWindow()) == hwnd:
        try:
            import mss

            with mss.mss() as screen:
                pixels = np.asarray(
                    screen.grab({"left": left, "top": top, "width": w, "height": h})
                )[:, :, :3].copy()
            if pixels.shape[:2] == (h, w):
                return pixels
        except Exception as exc:
            logger.debug("Desktop capture failed for foreground game; falling back to PrintWindow: {}", exc)

    hdc = user32.GetWindowDC(hwnd)
    mem = gdi32.CreateCompatibleDC(hdc)
    bmp = gdi32.CreateCompatibleBitmap(hdc, w, h)
    gdi32.SelectObject(mem, bmp)
    user32.PrintWindow(hwnd, mem, PW_RENDERFULLCONTENT)

    bmi = _BMIH(ctypes.sizeof(_BMIH), w, -h, 1, 32, 0, 0, 0, 0, 0, 0)
    buf = ctypes.create_string_buffer(w * h * 4)
    gdi32.GetDIBits(mem, bmp, 0, h, buf, ctypes.byref(bmi), 0)

    img = np.frombuffer(buf.raw, dtype=np.uint8).reshape(h, w, 4)[:, :, :3].copy()

    gdi32.DeleteObject(bmp)
    gdi32.DeleteDC(mem)
    user32.ReleaseDC(hwnd, hdc)

    return img


# ---------------------------------------------------------------------------
# Capture-health guard (TASK-026)
# ---------------------------------------------------------------------------


def frame_health(frame: np.ndarray) -> dict[str, float]:
    """Return capture-health metrics for *frame*.

    Keys:
      mean_brightness  - mean of grayscale (0..255); very low => black frame.
      non_black_ratio  - fraction of pixels with max(R,G,B) > 8.
      unique_ratio     - estimated fraction of distinct quantized (4-bit) colors;
                         computed from a bounded sample to keep 1080p capture fast.
    """
    if frame.size == 0:
        return {"mean_brightness": 0.0, "non_black_ratio": 0.0, "unique_ratio": 0.0}
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    mean_brightness = float(gray.mean())
    non_black_ratio = float(np.mean(frame.max(axis=2) > 8))
    total = frame.shape[0] * frame.shape[1]
    pixels = frame.reshape(-1, frame.shape[2])
    stride = max(1, math.ceil(total / 16_384))
    quantized = (pixels[::stride] >> 4).astype(np.uint16, copy=False)
    color_codes = (quantized[:, 0] << 8) | (quantized[:, 1] << 4) | quantized[:, 2]
    unique_count = int(np.unique(color_codes).size)
    unique_ratio = float(unique_count / total) if total else 0.0
    return {
        "mean_brightness": mean_brightness,
        "non_black_ratio": non_black_ratio,
        "unique_ratio": unique_ratio,
    }


# ---------------------------------------------------------------------------
# OCR helper
# ---------------------------------------------------------------------------

import pytesseract  # noqa: E402

pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

# ponytail: key/button whitelists live in moa.py (single source); arrows needed for FMV choice nav.

DEFAULT_MENU_KEYWORDS = frozenset(
    {
        "tutorial",
        "setting",
        "settings",
        "exit",
        "play",
        "start",
        "lobby",
        "create",
        "join",
        "continue",
        "cancel",
        "back",
        "close",
        "yes",
        "no",
        "confirm",
        "name",
        "host",
        "room",
        "code",
    }
)


def load_profile(name: str) -> dict[str, Any]:
    """Load a game profile from ``game_profiles.json``."""
    if not PROFILE_PATH.exists():
        raise FileNotFoundError(f"Profile file not found: {PROFILE_PATH}")
    data: dict[str, Any] = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
    if name not in data:
        available = ", ".join(data.keys())
        raise SystemExit(f"Profile {name!r} not found. Available: {available}")
    return cast("dict[str, Any]", data[name])


def ocr_frame(
    frame: np.ndarray, top_n: int = 15, *, psm: int = 3, scale: float = 1.5
) -> list[dict]:
    """Run pytesseract on *frame* and return the top *top_n* words with coords.

    The frame is upscaled x1.5 (LANCZOS) and thresholded before OCR.
    """
    big = cv2.resize(frame, None, fx=scale, fy=scale, interpolation=cv2.INTER_LANCZOS4)
    gray = cv2.cvtColor(big, cv2.COLOR_BGR2GRAY)
    _, th = cv2.threshold(gray, 140, 255, cv2.THRESH_BINARY)
    data = pytesseract.image_to_data(
        th, output_type=pytesseract.Output.DICT, config=f"--psm {psm}"
    )
    words: list[dict] = []
    for i, txt in enumerate(data["text"]):
        txt = txt.strip()
        if txt:
            words.append(
                {
                    "text": txt,
                    "x": round(data["left"][i] / scale),
                    "y": round(data["top"][i] / scale),
                    "w": round(data["width"][i] / scale),
                    "h": round(data["height"][i] / scale),
                }
            )
    return words[:top_n]


def ocr_fmv_frame(frame: np.ndarray, top_n: int = 40) -> list[dict]:
    """Read likely subtitle/choice text without scanning the cinematic image."""
    if frame.ndim != 3 or frame.size == 0:
        return []
    height, width = frame.shape[:2]
    x_offset, y_offset = round(width * 0.1), round(height * 0.65)
    x_end, y_end = round(width * 0.9), round(height * 0.93)
    padding = 40
    roi = frame[y_offset:y_end, x_offset:x_end]
    padded = cv2.copyMakeBorder(
        roi, padding, padding, padding, padding, cv2.BORDER_CONSTANT, value=(0, 0, 0)
    )
    # The FMV subtitle ROI is already tightly cropped. Keeping it at native
    # capture resolution avoids spending the choice timer on an unnecessary
    # 1.5x upscale, especially on 640x480 game windows.
    words = ocr_frame(padded, top_n=top_n, psm=6, scale=1.0)
    return [
        {
            **word,
            "x": max(0, word["x"] - padding) + x_offset,
            "y": max(0, word["y"] - padding) + y_offset,
        }
        for word in words
    ]


def ocr_menu_region(
    frame: np.ndarray,
    region: tuple[float, float, float, float] | list[float],
    top_n: int = 30,
) -> list[dict]:
    """OCR an English menu label area using normalized profile coordinates."""
    if len(region) != 4 or frame.ndim != 3 or frame.size == 0:
        raise ValueError("menu region needs a non-empty color frame and x/y/width/height")
    x, y, width, height = (float(value) for value in region)
    if (
        not all(np.isfinite(value) for value in (x, y, width, height))
        or x < 0
        or y < 0
        or width <= 0
        or height <= 0
        or x + width > 1
        or y + height > 1
    ):
        raise ValueError("normalized menu region must fit inside the frame")
    frame_h, frame_w = frame.shape[:2]
    left = int(round(x * frame_w))
    top = int(round(y * frame_h))
    right = min(frame_w, int(round((x + width) * frame_w)))
    bottom = min(frame_h, int(round((y + height) * frame_h)))
    crop = frame[top:bottom, left:right]
    if crop.size == 0:
        return []
    scale = 3.0
    enlarged = cv2.resize(crop, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    gray = cv2.cvtColor(enlarged, cv2.COLOR_BGR2GRAY)
    binary = cv2.threshold(gray, 175, 255, cv2.THRESH_BINARY)[1]
    data = pytesseract.image_to_data(
        binary,
        output_type=pytesseract.Output.DICT,
        config="--psm 6 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789",
    )
    words: list[dict] = []
    for index, raw_text in enumerate(data["text"]):
        text = str(raw_text).strip()
        if not text:
            continue
        confidence = float(data["conf"][index])
        if confidence < 0:
            continue
        words.append(
            {
                "text": text,
                "x": left + round(int(data["left"][index]) / scale),
                "y": top + round(int(data["top"][index]) / scale),
                "w": round(int(data["width"][index]) / scale),
                "h": round(int(data["height"][index]) / scale),
            }
        )
    return words[:top_n]


def build_ocr_context(words: list[dict]) -> str | None:
    """Format OCR words into a context string for the VLM agent."""
    if not words:
        return None
    lines = ["OCR detected text on screen:"]
    for w in words:
        lines.append(f'  "{w.get("text", "")}" at ({w.get("x", 0)},{w.get("y", 0)})')
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Param normalization
# ---------------------------------------------------------------------------


def resolve_click_target(
    params: dict,
    ocr_words: list[dict],
    window_rect: tuple[int, int, int, int],
    menu_keywords: frozenset[str],
    frame_size: tuple[int, int] | None = None,
) -> tuple[int, int] | None:
    """Resolve absolute screen coords for a click target.

    1. If *params* already contain x,y → clamp into window and return.
    2. Find first OCR word whose text matches a menu keyword → word centre + window offset.
    3. Fallback: window centre.
    """
    left, top, right, bottom = window_rect
    win_w = right - left
    win_h = bottom - top
    frame_w, frame_h = frame_size or (win_w, win_h)
    scale_x = win_w / frame_w if frame_w else 1.0
    scale_y = win_h / frame_h if frame_h else 1.0

    # 1. Explicit coords in params
    if "x" in params and "y" in params:
        rx = int(params["x"])
        ry = int(params["y"])
        abs_x = max(left, min(left + round(rx * scale_x), right - 1))
        abs_y = max(top, min(top + round(ry * scale_y), bottom - 1))
        return abs_x, abs_y

    # 2. OCR menu-word match
    for w in ocr_words:
        text = w["text"].lower()
        if any(_menu_keyword_matches(text, kw) for kw in menu_keywords):
            cx = left + round((w["x"] + w["w"] // 2) * scale_x)
            cy = top + round((w["y"] + w["h"] // 2) * scale_y)
            cx = max(left, min(cx, right - 1))
            cy = max(top, min(cy, bottom - 1))
            logger.info(
                "OCR menu target {!r} at ({}, {})",
                w["text"],
                cx,
                cy,
            )
            return cx, cy

    # 3. Fallback: window centre
    return left + win_w // 2, top + win_h // 2


def _menu_keyword_matches(text: str, keyword: str) -> bool:
    """Match exact OCR labels, tolerating merged spacing such as ``NEWGAME``."""
    compact_text = re.sub(r"[^\w]+", "", text.casefold())
    compact_keyword = re.sub(r"[^\w]+", "", keyword.casefold())
    return bool(compact_keyword and compact_keyword == compact_text)


def _phrase_boxes(phrases: list[str], words: list[dict]) -> list[tuple[str, int, int, int, int]]:
    """Locate exact OCR phrases and return their union boxes in frame pixels."""
    tokens = [
        (re.sub(r"[^\w]+", "", str(word.get("text", "")).casefold()), word)
        for word in words
    ]
    tokens = [(token, word) for token, word in tokens if token]
    found: list[tuple[str, int, int, int, int]] = []

    def adjacent_same_line(first: dict, second: dict) -> bool:
        first_h = max(1, int(first.get("h", 1)))
        second_h = max(1, int(second.get("h", 1)))
        first_center = int(first.get("y", 0)) + first_h / 2
        second_center = int(second.get("y", 0)) + second_h / 2
        if abs(first_center - second_center) > max(first_h, second_h) * 0.55:
            return False
        gap = int(second.get("x", 0)) - (
            int(first.get("x", 0)) + int(first.get("w", 0))
        )
        return 0 <= gap <= max(6, round(min(first_h, second_h) * 0.55))

    for phrase in phrases:
        target = re.sub(r"[^\w]+", "", phrase.casefold())
        if not target:
            continue
        for start in range(len(tokens)):
            combined = ""
            selected: list[dict] = []
            for token, word in tokens[start:]:
                combined += token
                selected.append(word)
                if len(combined) >= len(target):
                    if combined == target:
                            last_index = start + len(selected) - 1
                            embedded = (
                                start > 0
                                and adjacent_same_line(tokens[start - 1][1], selected[0])
                            ) or (
                                last_index + 1 < len(tokens)
                                and adjacent_same_line(selected[-1], tokens[last_index + 1][1])
                            )
                            if not embedded:
                                left = min(int(item.get("x", 0)) for item in selected)
                                top = min(int(item.get("y", 0)) for item in selected)
                                right = max(int(item.get("x", 0)) + int(item.get("w", 0)) for item in selected)
                                bottom = max(int(item.get("y", 0)) + int(item.get("h", 0)) for item in selected)
                                found.append((phrase, left, top, right, bottom))
                    break
    return found


def _fmv_action_grounded(
    action: Action,
    words: list[dict],
    choice_phrases: list[str],
    menu_keywords: frozenset[str],
    margin: int = 100,
) -> bool:
    """Only permit FMV inputs grounded on visible choices or exact menu labels."""
    if action.action == "noop" or action.action == "mouse_move":
        return True
    choice_boxes = _phrase_boxes(choice_phrases, words)
    menu_boxes = _phrase_boxes(list(menu_keywords), words)
    if action.action in {"key_press", "key_hold"}:
        return bool(choice_boxes)
    if action.action != "click":
        return False
    if "x" not in action.params or "y" not in action.params:
        # Coordinate-free clicks may only be resolved by a visible exact menu label.
        return bool(menu_boxes)
    x, y = int(action.params["x"]), int(action.params["y"])
    return any(
        left - margin <= x <= right + margin and top - margin <= y <= bottom + margin
        for _, left, top, right, bottom in [*choice_boxes, *menu_boxes]
    )


def normalize_params(action: Action, frame_size: tuple[int, int] | None = None) -> Action:
    """Normalize and validate action params before dispatch.

    - key_name → key
    - Whitelist keys; replace with noop on violation
    - Whitelist click buttons; replace with noop on violation
    """
    if not isinstance(action.params, dict):
        return Action("noop", {})
    params = dict(action.params)
    allowed_params = {
        "key_press": {"key", "key_name"},
        "mouse_move": {"x", "y"},
        "click": {"button", "x", "y"},
        "type_text": {"text"},
        "noop": set(),
    }
    if action.action not in allowed_params or set(params) - allowed_params[action.action]:
        logger.warning("Action {!r} has unsupported name/params, replacing with noop", action.action)
        return Action("noop", {})

    # Normalize key name
    if "key_name" in params and "key" not in params:
        params["key"] = params.pop("key_name")

    if action.action == "key_press":
        if "key" in params and "key_name" in params:
            return Action("noop", {})
        key = params.get("key", params.get("key_name", ""))
        if not isinstance(key, str):
            return Action("noop", {})
        key = key.lower()
        if not key:
            logger.warning("key_press has no key param, replacing with noop")
            return Action(action="noop", params={})
        if key not in ALLOWED_KEYS:
            logger.warning("Key {!r} not in whitelist, replacing with noop", key)
            return Action(action="noop", params={})
        params["key"] = key

    if action.action == "click":
        button = params.get("button", "left")
        if not isinstance(button, str):
            return Action("noop", {})
        button = button.lower()
        if button not in ALLOWED_BUTTONS:
            logger.warning("Button {!r} not in whitelist, replacing with noop", button)
            return Action(action="noop", params={})
        params["button"] = button

    if action.action in {"mouse_move", "click"} and ("x" in params or "y" in params):
        if "x" not in params or "y" not in params:
            return Action("noop", {})
        try:
            x, y = params["x"], params["y"]
            if isinstance(x, bool) or isinstance(y, bool):
                return Action("noop", {})
            fx, fy = float(x), float(y)
            if not np.isfinite(fx) or not np.isfinite(fy):
                return Action("noop", {})
            if frame_size is not None:
                width, height = frame_size
                if not (0 <= fx < width and 0 <= fy < height):
                    return Action("noop", {})
            params.update(x=round(fx), y=round(fy))
        except (TypeError, ValueError):
            return Action("noop", {})

    if action.action == "mouse_move" and ("x" not in params or "y" not in params):
        return Action("noop", {})

    if action.action == "type_text":
        text = params.get("text")
        if not isinstance(text, str) or not text or len(text) > 32 or not all(c.isprintable() for c in text):
            logger.warning("type_text with invalid text, replacing with noop")
            return Action(action="noop", params={})
        params["text"] = text

    return Action(action=action.action, params=params)


# ---------------------------------------------------------------------------
# Kill-switch
# ---------------------------------------------------------------------------


def _is_f12_pressed() -> bool:
    """Return True when the user taps F12."""
    return bool(user32.GetAsyncKeyState(VK_F12) & 0x8000)


# ---------------------------------------------------------------------------
# LiveGameplayAgent: stateful per-step loop driver (testable)
# ---------------------------------------------------------------------------


def _scale_decision_action(action: Action, decision_shape: tuple[int, ...], capture_shape: tuple[int, ...]) -> Action:
    """Map coordinates from a downscaled VLM image back to captured pixels."""
    if action.action not in {"click", "mouse_move"} or "x" not in action.params or "y" not in action.params:
        return action
    decision_h, decision_w = decision_shape[:2]
    capture_h, capture_w = capture_shape[:2]
    if decision_w <= 0 or decision_h <= 0:
        return action
    params = dict(action.params)
    params["x"] = round(float(params["x"]) * capture_w / decision_w)
    params["y"] = round(float(params["y"]) * capture_h / decision_h)
    return Action(action.action, params)


def _scale_ocr_words(words: list[dict], source_shape: tuple[int, ...], target_shape: tuple[int, ...]) -> list[dict]:
    """Map OCR word boxes from a resized image into captured-frame pixels."""
    source_h, source_w = source_shape[:2]
    target_h, target_w = target_shape[:2]
    if source_w <= 0 or source_h <= 0:
        return words
    scale_x, scale_y = target_w / source_w, target_h / source_h
    scaled_words: list[dict] = []
    for word in words:
        scaled = {
            **word,
            "x": round(word["x"] * scale_x),
            "y": round(word["y"] * scale_y),
        }
        if "w" in word:
            scaled["w"] = round(word["w"] * scale_x)
        if "h" in word:
            scaled["h"] = round(word["h"] * scale_y)
        scaled_words.append(scaled)
    return scaled_words


def _scenario_choice_hints(scenario: dict[str, Any] | None) -> tuple[str, ...]:
    """Extract only explicitly requested branch labels for visual fallback."""
    if not isinstance(scenario, dict):
        return ()
    values: list[Any] = []
    for key in ("choice", "expected_choice"):
        values.append(scenario.get(key))
    for key in ("choices", "expected_choices"):
        raw = scenario.get(key, [])
        values.extend(raw if isinstance(raw, list) else [raw])
    steps = scenario.get("steps", [])
    if isinstance(steps, list):
        for step in steps:
            if isinstance(step, dict):
                values.extend((step.get("choice"), step.get("expected_choice")))
    return tuple(dict.fromkeys(
        value.strip() for value in values if isinstance(value, str) and value.strip()
    ))


class LiveGameplayAgent:
    """Encapsulates the per-step decision/dispatch/reward/stuck-recovery loop.

    Splitting this out of :func:`main` makes the stuck-detection and ranked
    alternative auto-dispatch logic unit-testable with mocked collaborators.
    """

    def __init__(
        self,
        *,
        agent: "VLMAgent | MOAAgent",
        cache: "SkillCache",
        executor: ActionExecutor,
        reward_fn: "FrameDiffReward",
        window_rect: tuple[int, int, int, int],
        menu_keywords: frozenset[str],
        win_w: int,
        win_h: int,
        trace_path: Path,
        strategy: str = "menu_nav",
        loop_window: int = 4,
        consecutive_failure_limit: int = 3,
        backoff_seconds: float = 30.0,
        capture_warn_threshold: float = 0.02,
        freeze_warn: bool = True,
        stale_frame_max_age_seconds: float = 2.0,
        state_oracle: ProfileStateOracle | None = None,
        visual_choice_hints: tuple[str, ...] = (),
    ) -> None:
        self._agent = agent
        self._cache = cache
        self._executor = executor
        self._reward_fn = reward_fn
        self._window_rect = window_rect
        self._strategy = strategy
        # realtime_flick (action) games have no menus, so OCR menu-keyword
        # matching must be disabled regardless of the profile's keyword list.
        self._menu_keywords = frozenset() if strategy == "realtime_flick" else menu_keywords
        self._win_w = win_w
        self._win_h = win_h
        self._frame_size: tuple[int, int] | None = None
        self._trace_path = trace_path
        self._loop_window = loop_window
        self._consecutive_failure_limit = consecutive_failure_limit
        self._backoff_seconds = backoff_seconds
        self._consecutive_failed_steps = 0
        self.halted = False
        self._capture_warn_threshold = capture_warn_threshold
        self._freeze_warn = freeze_warn
        self._stale_frame_max_age_seconds = stale_frame_max_age_seconds
        self._state_oracle = state_oracle
        self._visual_choice_hints = visual_choice_hints
        self._last_state_recognition: dict[str, Any] | None = None
        self._last_dispatch_target: dict[str, int] | None = None

        # TASK-026: capture-health guard state
        self._prev_capture_hash: str | None = None
        self._last_capture_health: dict[str, float] | None = None

        # loop-guard state
        self._recent_actions: deque[tuple[str, dict, str]] = deque(maxlen=loop_window)

        # stuck-recovery state
        self._consecutive_zero_reward = 0
        # TASK-021: consecutive zero-reward steps + OCR-part observability
        self._zero_streak = 0
        self._last_ocr_part: str | None = None
        self._tried_alternative = False

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _dispatch_action(self, action: Action, ocr_words: list[dict]) -> Action:
        """Normalize, resolve click target, clamp, then dispatch *action*.

        Returns the (possibly transformed) action that was actually dispatched
        so callers can compare it against alternatives.
        """
        action = normalize_params(action, self._frame_size)
        self._last_dispatch_target = None

        if self._strategy == "fmv_passive" and action.action in {
            "click", "key_press", "key_hold", "type_text"
        }:
            state = self._last_state_recognition or {}
            if self._visual_choice_hints:
                # A scenario names the one route under test. This applies to
                # OCR and VLM evidence alike; generic subtitle words such as
                # "right" must not authorize a sibling route.
                matched_choices = list(self._visual_choice_hints)
            else:
                matched_choices = [
                    str(match.get("text", ""))
                    for match in state.get("matches", [])
                    if match.get("kind") == "story_choice"
                ]
            if not _fmv_action_grounded(
                action, ocr_words, matched_choices, self._menu_keywords
            ):
                logger.warning("FMV input blocked: no visible choice/menu target grounds this action")
                action = Action("noop", {})

        # FMV playback is passive by default. A generic click has no reliable
        # target and can skip a scene or toggle playback, so require coordinates
        # from a grounded vision decision or OCR-grounded menu text.
        if (
            self._strategy == "fmv_passive"
            and action.action == "click"
            and not ("x" in action.params and "y" in action.params)
            and not _fmv_action_grounded(
                action, ocr_words, [], self._menu_keywords
            )
        ):
            logger.warning("FMV passive policy blocked an ungrounded click")
            action = Action("noop", {})

        if action.action == "click":
            target = None
            if self._strategy == "fmv_passive" and self._visual_choice_hints:
                # For a scenario-pinned branch, snap the model's approximate
                # click to the center of that exact OCR/VLM-grounded label.
                # This avoids clicking just outside a small visible button.
                target_boxes = _phrase_boxes(list(self._visual_choice_hints), ocr_words)
                if target_boxes:
                    _, left, top, right, bottom = target_boxes[0]
                    target = ((left + right) // 2, (top + bottom) // 2)
            if target is None:
                target = resolve_click_target(
                    action.params,
                    ocr_words,
                    self._window_rect,
                    self._menu_keywords,
                    self._frame_size,
                )
            if target is not None:
                mx, my = target
                left, top, _, _ = self._window_rect
                self._last_dispatch_target = {
                    "screen_x": int(mx),
                    "screen_y": int(my),
                    "window_x": int(mx - left),
                    "window_y": int(my - top),
                }
                action = Action(
                    action="click",
                    params={
                        "button": action.params.get("button", "left"),
                        "x": int(mx),
                        "y": int(my),
                    },
                )

        if action.action == "mouse_move":
            rx = int(action.params.get("x", 0))
            ry = int(action.params.get("y", 0))
            left, top, right, bottom = self._window_rect
            frame_w, frame_h = self._frame_size or (self._win_w, self._win_h)
            rx = round(rx * self._win_w / frame_w) if frame_w else rx
            ry = round(ry * self._win_h / frame_h) if frame_h else ry
            abs_x = max(left, min(left + rx, right - 1))
            abs_y = max(top, min(top + ry, bottom - 1))
            action = Action(action="mouse_move", params={"x": abs_x, "y": abs_y})

        self._executor.dispatch(action)
        return action

    def step(
        self,
        frame: np.ndarray,
        ocr_words: list[dict],
        next_frame: np.ndarray,
        *,
        frame_captured_at: float | None = None,
        decision_frame: np.ndarray | None = None,
    ) -> float:
        """Run one observe/decide/dispatch/reward iteration.

        Returns the computed reward for the step.
        """
        if self.halted:
            return 0.0
        self._last_state_recognition = None
        if frame_captured_at is not None:
            frame_age = time.monotonic() - frame_captured_at
            if frame_age < 0 or frame_age > self._stale_frame_max_age_seconds:
                reason = "stale observation; input skipped"
                logger.warning("{} age={:.3f}s", reason, frame_age)
                self._write_trace(
                    sig="stale-frame",
                    action="skip",
                    params={"reason": reason, "age_seconds": frame_age},
                    cached=False,
                    reward=0.0,
                    alt_action=None,
                )
                return 0.0
        # 0. capture-health guard (TASK-026): skip black/empty captures so a bad
        # PrintWindow/mss capture does not pollute the VLM/MOA or skill cache.
        h = frame_health(frame)
        self._frame_size = (frame.shape[1], frame.shape[0]) if frame.size else None
        self._last_capture_health = h
        frame_hash = _visual_hash(frame)

        if h["non_black_ratio"] < self._capture_warn_threshold:
            logger.warning(
                "capture health: near-black frame (non_black_ratio={})",
                h["non_black_ratio"],
            )
            self._prev_capture_hash = frame_hash
            # Still record the skipped step so it is visible in the session report
            # (a silent early-return would otherwise vanish from the trace).
            self._write_trace(
                sig="black-frame",
                action="skip",
                params={"reason": "near-black capture", **h},
                cached=False,
                reward=0.0,
                alt_action=None,
            )
            return 0.0

        if self._freeze_warn and frame_hash == self._prev_capture_hash:
            logger.warning(
                "capture health: frame unchanged since last step (possible capture freeze)"
            )
        self._prev_capture_hash = frame_hash

        # 0b. strategy observability (TASK-024)
        logger.info("strategy={}", self._strategy)

        # FMV input is allowed only on a screen grounded by this game's
        # imported subtitle/choice data or explicit profile menu cues. For a
        # testcase that names a branch, allow strict VLM visual grounding when
        # OCR misses a stylized choice overlay.
        state: dict[str, Any] | None = None
        if self._strategy == "fmv_passive":
            state = (
                self._state_oracle.recognize(ocr_words)
                if self._state_oracle is not None
                else {"known": False, "profile": "unconfigured", "scene_ids": [], "matches": []}
            )
            if (
                not state.get("known", False)
                and self._visual_choice_hints
                and self._state_oracle is not None
                and callable(getattr(self._agent, "detect_visible_story_choices", None))
            ):
                visual_choices = self._agent.detect_visible_story_choices(
                    frame,
                    self._state_oracle.visual_choice_candidates(self._visual_choice_hints),
                )
                if visual_choices:
                    ocr_words.extend(visual_choices)
                    state = self._state_oracle.recognize(ocr_words)
                    if state.get("known", False):
                        state["evidence_source"] = "vlm_visual_choice"
                        state["visual_choice_labels"] = [item["text"] for item in visual_choices]
                        logger.info("VLM grounded visible FMV choices: {}", state["visual_choice_labels"])
            self._last_state_recognition = state
            if not state.get("known", False):
                sig = signature(ocr_words, frame=frame)
                self._write_trace(
                    sig=sig,
                    action="skip",
                    params={
                        "reason": "unknown screen; FMV input skipped",
                        "oracle_profile": state.get("profile", "unconfigured"),
                    },
                    cached=False,
                    reward=0.0,
                    alt_action=None,
                )
                return 0.0

        # 1. OCR + visual-evidence context. Coordinates must match the image
        # seen by the VLM (which may be downscaled); action coords are mapped
        # back to capture pixels after the decision.
        decision_frame = decision_frame if decision_frame is not None else frame
        context_words = _scale_ocr_words(ocr_words, frame.shape, decision_frame.shape)
        context = build_ocr_context(context_words)
        sig = signature(ocr_words, frame=frame)

        # 2. observe + decide
        obs = self._agent.observe(decision_frame)
        action: Action = self._agent.decide(
            observation=obs,
            context=context,
            state_sig=sig,
            strategy=self._strategy,
            menu_keywords=list(self._menu_keywords),
        )
        action = _scale_decision_action(action, decision_frame.shape, frame.shape)
        logger.info("Action: {}  params: {}", action.action, action.params)

        # A failed/invalid decision is a stop condition for this step. Do this
        # before strategy fallbacks (for example VN click-to-advance) can turn
        # a safe noop into an input event.
        if isinstance(self._agent, MOAAgent):
            decision_failed = not self._agent.last_decision_succeeded
        else:
            decision_failed = self._agent.consecutive_fallbacks > 0
        if decision_failed:
            self._consecutive_failed_steps += 1
            reason = "decision backend/validation failure"
            if self._consecutive_failed_steps >= self._consecutive_failure_limit:
                self.halted = True
                reason += "; failure limit reached, stopped safely"
                logger.error("{}", reason)
            else:
                logger.warning("{}; skipping input for this step", reason)
            self._write_trace(
                sig=sig,
                action="skip",
                params={"reason": reason, "failure_count": self._consecutive_failed_steps},
                cached=False,
                reward=0.0,
                alt_action=None,
            )
            return 0.0
        self._consecutive_failed_steps = 0

        # 2b. per-strategy action policy (TASK-024)
        if self._strategy == "vn_advance" and action.action == "noop":
            # Visual novels are advanced by clicking; a no-op decision should
            # fall back to a click to advance dialogue rather than stall.
            action = Action(action="click", params={"button": "left"})

        # 4. loop guard: detect repeated identical actions on same screen
        vh = _visual_hash(frame)
        self._recent_actions.append((action.action, dict(action.params), vh))
        if self._strategy != "fmv_passive" and len(self._recent_actions) == self._loop_window:
            all_same_action = all(
                a[0] == self._recent_actions[0][0] and a[1] == self._recent_actions[0][1]
                for a in self._recent_actions
            )
            all_same_frame = all(a[2] == vh for a in self._recent_actions)
            if all_same_action and all_same_frame:
                logger.warning(
                    "Loop detected: same action {} repeated {} times"
                    " on unchanged screen - injecting variation",
                    action.action,
                    self._loop_window,
                )
                self._dispatch_action(
                    Action("mouse_move", {"x": self._win_w // 2, "y": self._win_h // 2}),
                    ocr_words,
                )
                time.sleep(0.2)
                action = Action(action="click", params={"button": "left"})
                self._recent_actions.clear()

        # 5. dispatch the decided action through normalize/resolve/clamp
        executed = self._dispatch_action(action, ocr_words)

        # 6. reward signal from next frame
        if next_frame.size == 0:
            logger.error("next frame is empty; stopping before reward calculation")
            self._write_trace(
                sig=sig,
                action="skip",
                params={"reason": "empty next-frame capture"},
                cached=False,
                reward=0.0,
                alt_action=None,
            )
            return 0.0
        reward = self._reward_fn.update(next_frame)
        self._agent.learn(reward, done=False)
        # Reward-weighted feedback: feed the observed frame-diff reward back into
        # the MOA so actions that change the screen gain vote influence over time.
        if isinstance(self._agent, MOAAgent):
            from qa_framework.gameplay_agent.moa import _action_signature

            self._agent.update_rewards({_action_signature(executed): reward})
        # Frame difference is useful for diagnostics/stuck detection, but it is
        # not a QA oracle and must never certify a reusable cached action.
        logger.info("reward={:.1f}  changed={}", reward, self._reward_fn.changed)

        # --- TASK-021: ranked alternative auto-dispatch ----------------------
        ocr_part = SkillCache._ocr_part(sig)
        # A change in OCR state resets the stuck streak + alternative guard.
        if ocr_part != self._last_ocr_part:
            self._zero_streak = 0
            self._tried_alternative = False
            self._last_ocr_part = ocr_part

        if reward == 0.0:
            self._zero_streak += 1
        else:
            self._zero_streak = 0
            self._tried_alternative = False

        dispatched_alt: str | None = None
        if (
            self._strategy != "fmv_passive"
            and reward == 0.0
            and self._zero_streak >= 2
            and not self._tried_alternative
        ):
            alts = self._cache.rank_by_ocr(ocr_part, top_k=3)
            if alts:
                top = alts[0]
                alt_action = Action(top["action"], top.get("params", {}))
                if alt_action != executed:
                    self._dispatch_action(alt_action, ocr_words)
                    self._tried_alternative = True
                    dispatched_alt = alt_action.action
                    logger.info(
                        "trying ranked alternative: {} (ratio={:.2f})",
                        alt_action.action,
                        top["ratio"],
                    )
                # else: alternative equals the action already executed; treat as
                # if no usable alternative exists (fall through to escape).

        # --- stuck-state recovery: inject escape fallback --------------------
        if reward == 0.0:
            self._consecutive_zero_reward += 1
        else:
            self._consecutive_zero_reward = 0

        # Only fall back to escape when no ranked alternative was dispatched.
        # realtime_flick (action) games have no menus, so escape is meaningless.
        if (
            self._consecutive_zero_reward >= 3
            and not self._tried_alternative
            and self._strategy not in {"realtime_flick", "fmv_passive"}
        ):
            logger.warning(
                "stuck: injecting escape ({} consecutive zero rewards)",
                self._consecutive_zero_reward,
            )
            self._executor.dispatch(Action(action="key_press", params={"key": "escape"}))
            self._consecutive_zero_reward = 0
            time.sleep(0.5)

        # 7. trace entry
        self._write_trace(
            sig=sig,
            action=executed.action,
            params=executed.params,
            cached=False,
            reward=reward,
            alt_action=dispatched_alt,
        )

        return reward

    def _write_trace(
        self,
        *,
        sig: str,
        action: str,
        params: dict,
        cached: bool,
        reward: float,
        alt_action: str | None,
    ) -> None:
        """Append one JSONL trace entry (used by both normal and skipped steps)."""
        trace_entry = {
            "sig": sig,
            "action": action,
            "params": params,
            "cached": cached,
            "reward": reward,
            "alt_action": alt_action,
        }
        if self._last_state_recognition is not None:
            trace_entry["state_recognition"] = self._last_state_recognition
        if self._last_dispatch_target is not None:
            trace_entry["dispatch_target"] = self._last_dispatch_target
        with self._trace_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(trace_entry, ensure_ascii=False) + "\n")
            f.flush()


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

ALLOWED_ACTIONS = ["key_press", "mouse_move", "click", "type_text", "noop"]
DEFAULT_MAX_STEPS = 10
# ponytail: brief frame-stability delay before observe/decide, not a per-action pause.
STEP_DELAY = 0.25
STEP_DELAY_MIN = 0.0
STEP_DELAY_MAX = 30.0
SYSTEM_PROMPT_TEMPLATE = (
    "You are controlling the {game_name} game. "
    "Observe the screenshot and decide the single best action to take next. "
    'Return exactly one JSON object: {{"action": "...", "params": {{...}}}}. '
    "mouse_move params use x,y relative to the window top-left corner. "
    "click params use button (left/right/middle). "
    "key_press params use a key name (e.g. w, a, s, d, space, enter, escape, arrow_up, arrow_down, arrow_left, arrow_right). "
    "type_text params use a text string (up to 32 printable characters)."
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Live gameplay agent: capture game window and drive it via VLMAgent.",
    )
    parser.add_argument(
        "--profile",
        default="agent-veil",
        help="Game profile name from game_profiles.json (default: %(default)s).",
    )
    parser.add_argument(
        "--max-steps",
        type=int,
        default=DEFAULT_MAX_STEPS,
        help="Maximum number of decide/execute iterations (default: %(default)s).",
    )
    parser.add_argument(
        "--base-url",
        default="http://localhost:1234/v1",
        help="LM Studio / OpenAI-compatible base URL (default: %(default)s).",
    )
    parser.add_argument(
        "--model",
        default="qwen/qwen2.5-vl-7b",
        help="Model name served by the backend (default: %(default)s).",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=90.0,
        help="VLM request timeout in seconds (default: %(default)s).",
    )
    parser.add_argument(
        "--structured-output",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Request LM Studio JSON-Schema output (default: enabled); use --no-structured-output for servers without support.",
    )
    parser.add_argument(
        "--step-delay",
        type=float,
        default=STEP_DELAY,
        help="Frame-stability delay in seconds before each observe/decide step "
        "(0..30, default: %(default)s). Profile 'step_delay' applies only when "
        "this flag is not passed explicitly.",
    )
    parser.add_argument(
        "--trace-path",
        type=Path,
        help="Optional run-specific JSONL trace destination.",
    )
    parser.add_argument(
        "--report-path",
        type=Path,
        help="Optional run-specific HTML report destination.",
    )
    parser.add_argument(
        "--scenario-file",
        type=Path,
        help="Optional local testcase scenario JSON used to guide this bounded run.",
    )
    parser.add_argument(
        "--moa",
        action="store_true",
        help=(
            "Use a Mixture-of-Agents: query qwen/qwen2.5-vl-7b (1.0), "
            "google/gemma-4-e2b (0.6) and qwen/qwen3.8-27b (0.4) in parallel. "
            "Low-latency early-exit waits for the fast primary VLM, and votes "
            "are reward-weighted from observed frame-diff rewards."
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    # --- load game profile ---------------------------------------------------
    profile = load_profile(args.profile)
    window_title = profile["window_title"]
    game_type = profile.get("game_type", "menu")
    strategy = profile.get("strategy", "menu_nav")
    menu_keywords = frozenset(profile.get("menu_keywords", []))
    menu_ocr_region = profile.get("menu_ocr_region")
    exe_path = profile.get("exe_path", "")
    game_name = profile.get("window_title", args.profile)
    _cli_args = list(argv) if argv is not None else sys.argv[1:]
    step_delay = args.step_delay
    # ponytail: CLI wins when passed; otherwise an optional profile step_delay applies.
    if "--step-delay" not in _cli_args and isinstance(profile.get("step_delay"), (int, float)):
        step_delay = float(profile["step_delay"])
    if not (STEP_DELAY_MIN <= step_delay <= STEP_DELAY_MAX):
        raise SystemExit(f"--step-delay must be between {STEP_DELAY_MIN} and {STEP_DELAY_MAX}.")
    logger.info(
        "profile={} game_type={} strategy={} step_delay={}",
        args.profile,
        game_type,
        strategy,
        step_delay,
    )

    # --- locate game window -------------------------------------------------
    wins = find_game_hwnd(window_title)
    if not wins:
        msg = (
            f"Game window not found.  Make sure {game_name} is running "
            f"and its title contains '{window_title}'."
        )
        if exe_path:
            msg += f"\nExpected exe: {exe_path}"
        logger.error(msg)
        return 1

    hwnd, title = wins[0]
    if not focus_game_window(hwnd):
        logger.error("Could not focus game window; no gameplay input was sent")
        return 1
    left, top, right, bottom = get_window_rect(hwnd)
    win_w = right - left
    win_h = bottom - top
    logger.info("Found window {!r}  rect=({},{},{},{})", title, left, top, right, bottom)

    # --- build VLM backend + agent ------------------------------------------
    cache_path = Path(f".ai/a2a/skills_{args.profile}.json")
    cache = SkillCache(path=cache_path)
    system_prompt = SYSTEM_PROMPT_TEMPLATE.format(game_name=game_name)
    scenario: dict[str, Any] | None = None
    if args.scenario_file is not None:
        scenario = json.loads(args.scenario_file.read_text(encoding="utf-8"))
        system_prompt += (
            "\n\nBounded QA scenario (follow only the listed case steps; do not infer PASS):\n"
            + json.dumps(scenario, ensure_ascii=False, indent=2)
            + "\n"
            + str(scenario.get("guidance", ""))
            + "\nStop and use noop if the screen is ambiguous, an unapproved branch appears, "
            "or a prompt requires a human decision. Frame change is not PASS."
        )
    profile_guidance = profile.get("agent_guidance", "").strip()
    if profile_guidance:
        system_prompt = f"{system_prompt}\n\nGame-specific QA safety rules: {profile_guidance}"
    agent_cache = None if strategy == "fmv_passive" else cache

    if args.moa:
        # Mixture-of-Agents: a fast primary model cross-checked by two others.
        # Built via MOAAgent.from_backends so the (model, weight) spec list is the
        # single source of truth and the sub-agent construction loop lives in one place.
        moa_specs = [
            ("qwen/qwen2.5-vl-7b", 1.0),
            ("google/gemma-4-e2b", 0.6),
            ("qwen/qwen3.8-27b", 0.4),
        ]

        def _moa_backend_factory(model: str) -> OpenAICompatBackend:
            return OpenAICompatBackend(
                base_url=args.base_url,
                model=model,
                api_key="lm-studio",
                max_tokens=128,
                timeout=args.timeout,
                structured_output=args.structured_output,
            )

        agent: VLMAgent | MOAAgent = MOAAgent.from_backends(
            backend_factory=_moa_backend_factory,
            specs=moa_specs,
            allowed_actions=ALLOWED_ACTIONS,
            system_prompt=system_prompt,
            cache=agent_cache,
            strategy=strategy,
            menu_keywords=list(menu_keywords),
            early_exit=True,
            min_votes=1,
        )
        logger.info(
            "MOA enabled (early-exit low-latency, reward-weighted) with {} sub-agents: {}",
            len(moa_specs),
            moa_specs,
        )
        moa_errors = getattr(agent, "backend_errors", 0)
        logger.debug("MOA backend_errors trace observability: {}", moa_errors)
    else:
        backend = OpenAICompatBackend(
            base_url=args.base_url,
            model=args.model,
            api_key="lm-studio",
            max_tokens=128,
            timeout=args.timeout,
            structured_output=args.structured_output,
        )
        agent = VLMAgent(
            backend=backend,
            allowed_actions=ALLOWED_ACTIONS,
            system_prompt=system_prompt,
            cache=agent_cache,
            strategy=strategy,
            menu_keywords=list(menu_keywords),
        )
    executor = ActionExecutor()
    trace_path = args.trace_path or Path(f".ai/a2a/trace_{args.profile}.jsonl")
    trace_path.parent.mkdir(parents=True, exist_ok=True)

    # Do not click the center to focus FMV players: that can toggle playback.
    # Other game profiles retain the existing focus behavior.
    if strategy != "fmv_passive":
        cx, cy = left + win_w // 2, top + win_h // 2
        ms = executor._mouse  # noqa: SLF001 – access real MouseService
        ms.click(x=cx, y=cy, button="left")
        logger.info("Initial focus click at ({}, {})", cx, cy)
        time.sleep(0.5)

    # --- reward signal ------------------------------------------------------
    reward_fn = FrameDiffReward()

    # --- stateful loop driver ----------------------------------------------
    state_oracle = None
    if strategy == "fmv_passive":
        from app.database.database import profile_database_path

        try:
            state_oracle = ProfileStateOracle.from_database(
                args.profile,
                profile_database_path(args.profile),
                menu_cues=list(menu_keywords),
            )
            logger.info(
                "FMV known-screen oracle loaded for profile={} from {} cues",
                args.profile,
                len(state_oracle._cues),  # noqa: SLF001 – startup diagnostics
            )
        except (OSError, sqlite3.Error, ValueError) as exc:
            logger.error("FMV profile state oracle unavailable; all unknown screens will be skipped: {}", exc)

    live = LiveGameplayAgent(
        agent=agent,
        cache=cache,
        executor=executor,
        reward_fn=reward_fn,
        window_rect=(left, top, right, bottom),
        menu_keywords=menu_keywords,
        win_w=win_w,
        win_h=win_h,
        trace_path=trace_path,
        strategy=strategy,
        state_oracle=state_oracle,
        visual_choice_hints=_scenario_choice_hints(scenario),
    )

    # --- main loop ----------------------------------------------------------
    report_path = args.report_path or Path(".ai/a2a/report.html")
    frame = grab_frame(hwnd)
    frame_captured_at = time.monotonic()
    completed_steps = 0
    stopped_early_reason = None
    try:
        for step in range(1, args.max_steps + 1):
            if not focus_game_window(hwnd):
                logger.error("Game lost foreground focus; stopping without sending input")
                stopped_early_reason = "focus_lost"
                break
            current_rect = get_window_rect(hwnd)
            left, top, right, bottom = current_rect
            live._window_rect = current_rect
            live._win_w = right - left
            live._win_h = bottom - top
            if frame.size == 0:
                live._write_trace(
                    sig="empty-frame",
                    action="skip",
                    params={"reason": "empty current-frame capture"},
                    cached=False,
                    reward=0.0,
                    alt_action=None,
                )
                logger.error("Current frame is empty; stopping gameplay loop")
                stopped_early_reason = "empty_current_frame"
                break
            # kill-switch check
            if _is_f12_pressed():
                print("KILLED BY USER")
                return 0

            logger.info("Step {}/{}", step, args.max_steps)

            # FMV runs OCR and vision on a bounded 1280px-wide frame. At 1080p,
            # full-frame OCR was exceeding the stale-observation budget.
            decision_frame = frame
            if strategy == "fmv_passive" and frame.shape[1] > 1280:
                decision_frame = cv2.resize(frame, (1280, 720), interpolation=cv2.INTER_AREA)

            # OCR keeps source resolution but scans only likely subtitle/choice
            # and menu rows. This preserves small labels without full-frame cost.
            ocr_words = ocr_fmv_frame(frame) if strategy == "fmv_passive" else ocr_frame(frame)
            if (
                strategy == "fmv_passive"
                and menu_ocr_region is not None
                and state_oracle is not None
                and not state_oracle.recognize(ocr_words).get("known", False)
            ):
                # The illustrated title screen uses stylized white text over
                # bright panels; a narrow, profile-defined binary OCR pass
                # catches menu labels without weakening the unknown-screen gate.
                menu_words = ocr_menu_region(frame, menu_ocr_region)
                ocr_words.extend(menu_words)

            # brief frame-stability delay before observe/decide (not a per-action pause)
            if step < args.max_steps:
                time.sleep(step_delay)

            # capture next frame, then run one observe/decide/dispatch/reward step
            next_frame = grab_frame(hwnd)
            if next_frame.size == 0:
                live._write_trace(
                    sig="empty-frame",
                    action="skip",
                    params={"reason": "empty next-frame capture"},
                    cached=False,
                    reward=0.0,
                    alt_action=None,
                )
                logger.error("Next frame is empty; stopping gameplay loop")
                stopped_early_reason = "empty_next_frame"
                break
            live.step(
                frame,
                ocr_words,
                next_frame,
                frame_captured_at=frame_captured_at,
                decision_frame=decision_frame,
            )
            if live.halted:
                logger.error("Gameplay loop halted after repeated decision failures")
                stopped_early_reason = "decision_failures"
                break
            completed_steps += 1
            # The next-frame used for reward is captured before decision latency;
            # recapture after the VLM response so the next observation is current.
            frame = grab_frame(hwnd)
            frame_captured_at = time.monotonic()
    except KeyboardInterrupt:
        # Graceful shutdown: per-step trace lines are already flushed to disk,
        # so the recorded history is preserved even on an unattended crash/abort.
        print("interrupted by user")

    # --- auto-generate session report ---------------------------------------
    if trace_path.exists():
        _build_session_report(trace_path, report_path)
        logger.info("session report written: {}", report_path)
        print(f"session report written: {report_path}")

    if _is_f12_pressed():
        return 0

    logger.info("Completed {} of {} requested steps.", completed_steps, args.max_steps)
    if stopped_early_reason is not None:
        logger.error("Run stopped early: {}", stopped_early_reason)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
