from __future__ import annotations

import json
import math
import re
from typing import Any, Protocol

import numpy as np
from loguru import logger

from qa_framework.gameplay_agent.actions import Action
from qa_framework.gameplay_agent.base import GameplayAgent
from qa_framework.gameplay_agent.skill_cache import SkillCache

_SAFE_KEYS = frozenset({
    "w", "a", "s", "d", "space", "enter", "escape", "tab", "e", "q",
    "shift", "arrow_up", "arrow_down", "arrow_left", "arrow_right",
})
_SAFE_BUTTONS = frozenset({"left", "right", "middle"})
_STRATEGY_GUIDANCE = {
    "platformer_stealth": (
        "Use single, short actions. Before jumping or crossing an edge, verify visible footing, "
        "landing area, and hazards. If footing or patrol state is unclear, choose noop. Do not "
        "repeat movement into an unseen edge. Treat hiding, chase, fall, and checkpoint changes "
        "as separate states; never claim traversal success from frame motion alone."
    ),
    "fmv_passive": (
        "Allow video playback to continue without input. Interact only with choices or prompts "
        "grounded by the active testcase and source data."
    ),
}


def _validated_action(parsed: dict[str, Any], allowed_actions: list[str], observation: Any) -> Action | None:
    """Validate model output before it can reach an input service."""
    name = parsed.get("action")
    params = parsed.get("params")
    if not isinstance(name, str) or name not in allowed_actions or not isinstance(params, dict):
        return None
    allowed_params: dict[str, set[str]] = {
        "noop": set(), "key_press": {"key", "key_name"},
        "key_release": {"key", "key_name"}, "key_hold": {"key", "key_name"},
        "click": {"button", "x", "y"}, "mouse_move": {"x", "y"},
        "type_text": {"text"},
    }
    if name not in allowed_params or set(params) - allowed_params[name]:
        return None
    clean = dict(params)
    if name == "noop":
        return Action(name, {}) if not clean else None
    if name in {"key_press", "key_release", "key_hold"}:
        if "key" in clean and "key_name" in clean:
            return None
        key = clean.get("key", clean.get("key_name"))
        if not isinstance(key, str) or key.lower() not in _SAFE_KEYS:
            return None
        return Action(name, {"key": key.lower()})
    if name == "type_text":
        value = clean.get("text")
        if not isinstance(value, str) or not value or len(value) > 32 or not all(c.isprintable() for c in value):
            return None
        return Action(name, {"text": value})
    if name == "click":
        button = clean.get("button", "left")
        if not isinstance(button, str) or button.lower() not in _SAFE_BUTTONS:
            return None
        clean["button"] = button.lower()
        if ("x" in clean) != ("y" in clean):
            return None
        if "x" not in clean:
            return Action(name, {"button": clean["button"]})
    if name in {"click", "mouse_move"}:
        if "x" not in clean or "y" not in clean:
            return None
        try:
            x, y = clean["x"], clean["y"]
            if isinstance(x, bool) or isinstance(y, bool):
                return None
            fx, fy = float(x), float(y)
            if not math.isfinite(fx) or not math.isfinite(fy):
                return None
            height, width = observation.shape[:2]
            if not (0 <= fx < width and 0 <= fy < height):
                return None
        except (AttributeError, TypeError, ValueError, IndexError):
            return None
        clean.update(x=round(fx), y=round(fy))
        return Action(name, clean)
    return None


class VLMBackend(Protocol):
    """Protocol for VLM backends.

    A backend must implement ``complete(prompt: str, image: np.ndarray) -> str``,
    returning the model's raw text response.
    """

    def complete(self, prompt: str, image: np.ndarray) -> str: ...


def _extract_json_response(text: str) -> dict[str, Any] | None:
    """Try to extract a JSON object from *text*, tolerating markdown fences
    and surrounding content.  Returns ``None`` on failure."""
    # Strip markdown code fences ``` ... ```
    cleaned = re.sub(r"```(?:json)?\s*", "", text, flags=re.S)
    cleaned = re.sub(r"```\s*", "", cleaned)

    # Remove leading/trailing non-JSON text by finding the first { and last }
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None

    candidate = cleaned[start : end + 1]
    try:
        parsed: dict[str, Any] = json.loads(candidate)
    except json.JSONDecodeError:
        return None
    return parsed


class VLMAgent(GameplayAgent):
    """VLM-driven gameplay QA agent.

    Observes game frames and decides actions via a vision-language model.
    """

    def __init__(
        self,
        backend: VLMBackend,
        allowed_actions: list[str],
        system_prompt: str | None = None,
        max_history: int = 5,
        cache: SkillCache | None = None,
        strategy: str | None = None,
        menu_keywords: list[str] | None = None,
    ) -> None:
        self._backend = backend
        self._allowed_actions = allowed_actions
        self._system_prompt = system_prompt or ""
        self._max_history = max_history
        self._cache = cache
        self._strategy = strategy
        self._menu_keywords = list(menu_keywords) if menu_keywords else []
        self._history: list[dict[str, Any]] = []
        self._episode_log: list[dict[str, Any]] = []
        self._consecutive_fallbacks: int = 0

    # ------------------------------------------------------------------
    # GameplayAgent
    # ------------------------------------------------------------------

    def observe(self, frame: Any) -> Any:
        """Accept a game frame; VLMAgent does not process pixels directly."""
        return frame

    def detect_visible_story_choices(
        self,
        frame: np.ndarray,
        candidates: list[str] | tuple[str, ...],
        *,
        min_confidence: int = 75,
    ) -> list[dict[str, Any]]:
        """Use structured VLM vision to recover stylized choice overlays OCR misses.

        Only labels supplied by the profile-scoped source database are accepted;
        returned boxes are frame-bounded and carry provenance for the run trace.
        Backends without caller-defined structured output fail closed.
        """
        complete_json = getattr(self._backend, "complete_json", None)
        if not callable(complete_json) or not candidates or frame.ndim != 3 or frame.size == 0:
            return []

        labels = sorted({str(label).strip() for label in candidates if str(label).strip()})
        if not labels:
            return []
        label_by_key = {
            re.sub(r"[^\w]+", "", label.casefold()): label for label in labels
        }
        schema = {
            "type": "object",
            "properties": {
                "choices": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "label": {"type": "string", "enum": labels},
                            "x": {"type": "integer"},
                            "y": {"type": "integer"},
                            "w": {"type": "integer"},
                            "h": {"type": "integer"},
                            "confidence": {"type": "integer"},
                        },
                        "required": ["label", "x", "y", "w", "h", "confidence"],
                        "additionalProperties": False,
                    },
                }
            },
            "required": ["choices"],
            "additionalProperties": False,
        }
        prompt = (
            "Inspect this FMV frame for visible, clickable story-choice text overlays only. "
            "Do not treat dialogue, subtitles, signs, or objects as choices. "
            "Return only candidate labels that are visibly rendered as active choice options; "
            "return an empty choices array if none are clear. For each option, give a tight "
            "bounding box in source-frame pixels (x,y,w,h) and visual-reading confidence 0-100. "
            "Use exact candidate spelling. Candidate labels: " + json.dumps(labels, ensure_ascii=False)
        )
        try:
            raw = complete_json(
                prompt,
                frame,
                schema_name="visible_story_choices",
                schema=schema,
            )
            parsed = _extract_json_response(raw)
        except Exception as exc:
            logger.warning("Structured visual choice detection failed closed: {}", exc)
            return []

        detected = parsed.get("choices") if isinstance(parsed, dict) else None
        if not isinstance(detected, list):
            return []
        height, width = frame.shape[:2]
        accepted: list[dict[str, Any]] = []
        seen_labels: set[str] = set()
        for item in detected:
            if not isinstance(item, dict):
                continue
            key = re.sub(r"[^\w]+", "", str(item.get("label", "")).casefold())
            label = label_by_key.get(key)
            x, y, box_w, box_h, confidence = (
                item.get("x"), item.get("y"), item.get("w"), item.get("h"), item.get("confidence")
            )
            if label is None or any(type(value) is not int for value in (x, y, box_w, box_h, confidence)):
                continue
            if key in seen_labels:
                # Repeated labels make the target ambiguous; reject this vision result.
                return []
            if confidence < min_confidence or box_w < 8 or box_h < 8:
                continue
            if x < 0 or y < 0 or x + box_w > width or y + box_h > height:
                continue
            accepted.append({
                "text": label,
                "x": x,
                "y": y,
                "w": box_w,
                "h": box_h,
                "source": "vlm_visual_choice",
                "confidence": confidence,
            })
            seen_labels.add(key)
        return accepted

    @property
    def consecutive_fallbacks(self) -> int:
        """Number of consecutive decide() fallbacks (backend error or parse fail)."""
        return self._consecutive_fallbacks

    def decide(
        self,
        observation: Any,
        context: str | None = None,
        state_sig: str | None = None,
        strategy: str | None = None,
        menu_keywords: list[str] | None = None,
    ) -> Action:
        """Decide the next action.

        Tracks consecutive fallbacks (backend error or parse failure) in
        ``self.consecutive_fallbacks`` so callers can apply back-off logic.
        """
        """Build a structured prompt and ask the VLM backend for an action.

        Parameters:
            observation: The game frame (numpy array).
            context: Optional supplementary text (e.g. OCR words) appended
                to the prompt for grounding.
            state_sig: Optional pre-computed state signature for cache lookup.
        """
        # --- cache hit? ---
        if self._cache is not None and state_sig is not None:
            cached = self._cache.get_verified(state_sig)
            cached_action = (
                _validated_action(
                    {"action": cached.get("action"), "params": cached.get("params", {})},
                    self._allowed_actions,
                    observation,
                )
                if cached is not None
                else None
            )
            if cached_action is not None:
                logger.info("skill cache hit sig={}", state_sig)
                action = cached_action
                self._history.append({"action": action.action, "params": action.params})
                if len(self._history) > self._max_history:
                    self._history = self._history[-self._max_history :]
                return action
            # --- fuzzy cache hit via prefix match ---
            ocr_prefix = self._cache.extract_ocr_prefix(state_sig)
            fuzzy = self._cache.best_sig_prefix(ocr_prefix)
            fuzzy_action = (
                _validated_action(
                    {"action": fuzzy.get("action"), "params": fuzzy.get("params", {})},
                    self._allowed_actions,
                    observation,
                )
                if fuzzy is not None
                else None
            )
            if fuzzy_action is not None:
                logger.info("fuzzy cache hit prefix={}", ocr_prefix)
                action = fuzzy_action
                self._history.append({"action": action.action, "params": action.params})
                if len(self._history) > self._max_history:
                    self._history = self._history[-self._max_history :]
                return action

        # --- build prompt ---
        parts: list[str] = []

        if self._system_prompt:
            parts.append(self._system_prompt)

        # --- genre/strategy context -----------------------------------------
        # Per TASK-024: pass the game's strategy + menu keywords into the prompt
        # so the VLM understands the genre it is controlling.
        effective_strategy = strategy or self._strategy
        effective_keywords = menu_keywords if menu_keywords is not None else self._menu_keywords
        if effective_strategy:
            parts.append(
                f"Genre/strategy context: this is a '{effective_strategy}' game. "
                "Adapt your decision-making to this genre."
            )
            if effective_keywords:
                parts.append(
                    "Relevant on-screen keywords to look for: " + ", ".join(effective_keywords)
                )
            strategy_guidance = _STRATEGY_GUIDANCE.get(effective_strategy)
            if strategy_guidance:
                parts.append("Strategy safety rules: " + strategy_guidance)

        parts.append(
            "You are a gameplay QA agent. Observe the frame and output exactly one action as JSON. "
            "For click, params MUST contain integer x and y pixel coordinates separately "
            "(never a coordinate array); button may be left, right or middle. "
            "For mouse_move, params MUST contain integer x and y. "
            "For key actions, params MUST be {\"key\":\"...\"}. "
            "For noop, params MUST be {}. Do not add fields."
        )
        parts.append('{"action": "...", "params": {}}')

        # allowed actions list
        parts.append("Allowed actions: " + ", ".join(self._allowed_actions))

        # recent history (bounded)
        if self._history:
            parts.append("Recent action history:")
            for entry in self._history[-self._max_history :]:
                parts.append(f"- {entry}")

        # OCR / external context
        if context:
            parts.append(context)

        prompt = "\n".join(parts)

        # --- call backend ---
        # observation is the frame; we expect a numpy array (BGR)
        try:
            raw = self._backend.complete(prompt, observation)
        except Exception as exc:
            logger.error("VLM backend error: {}", exc)
            self._consecutive_fallbacks += 1
            action = Action("noop", {})
            self._episode_log.append({"reward": 0.0, "done": False})
            return action

        # --- parse JSON response ---
        parsed = _extract_json_response(raw)
        action = _validated_action(parsed, self._allowed_actions, observation) if parsed is not None else None
        if action is not None:
            self._consecutive_fallbacks = 0
        else:
            self._consecutive_fallbacks += 1
            action = Action("noop", {})
            logger.warning("VLM response invalid or unsafe; returning noop", extra={"raw_response": raw})

        # record history
        if self._consecutive_fallbacks == 0:
            self._history.append({"action": action.action, "params": action.params})
        # keep bounded
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history :]

        # cache successful action
        if self._cache is not None and state_sig is not None and self._consecutive_fallbacks == 0:
            self._cache.put(state_sig, {"action": action.action, "params": action.params})

        return action

    def learn(self, reward: float, done: bool) -> None:
        """No-op; append reward info to the internal episode log."""
        self._episode_log.append({"reward": reward, "done": done})
