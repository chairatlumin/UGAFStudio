from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from qa_framework.gameplay.runner import GameplayRunConfig


def _as_path(value: Any) -> Path | None:
    if isinstance(value, str) and value.strip():
        return Path(value)
    if isinstance(value, Path):
        return value
    return None


def load_run_config(path: str | Path) -> GameplayRunConfig:
    """Load a gameplay run configuration from a JSON suite file.

    The file keeps game-specific paths, timeouts, and visual-assertion
    thresholds out of the Python code. Expected keys (all optional):

    * ``timeout`` (float, seconds)
    * ``executable_name`` (str) — disambiguate when multiple ``.exe`` exist
    * ``monitor_index`` (int)
    * ``assertions`` (list of assertion config dicts)
    * ``steam_root`` (str) — override the Steam library root for discovery
    * ``capture_poll_seconds`` (float) — re-capture until assertions pass
      within this budget (handles intro videos / loading screens)
    * ``actions`` (list) — foreground input actions between launch and checks
    * ``bot`` (object) — bounded autonomous gameplay episode settings
    """
    suite_path = Path(path).resolve()
    data = json.loads(suite_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Gameplay suite root must be a JSON object.")

    assertions = data.get("assertions", [])
    if not isinstance(assertions, list):
        raise ValueError("'assertions' must be a list.")

    return _config_from_dict(data, suite_path.parent)


def load_runs_config(path: str | Path) -> list[GameplayRunConfig]:
    """Load a combined suite that lists multiple game run configs.

    The top-level ``games`` key holds an array of run configs; if absent the
    file is treated as a single run config.
    """
    suite_path = Path(path).resolve()
    data = json.loads(suite_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Combined suite root must be a JSON object.")

    games = data.get("games")
    if games is None:
        return [load_run_config(suite_path)]
    if not isinstance(games, list) or not games:
        raise ValueError("Combined suite 'games' must be a non-empty list.")

    configs: list[GameplayRunConfig] = []
    for index, entry in enumerate(games):
        if not isinstance(entry, dict):
            raise ValueError(f"Game entry at index {index} must be an object.")
        configs.append(_config_from_dict(entry, suite_path.parent))
    return configs


def combined_steam_root(path: str | Path) -> Path | None:
    """Return the top-level ``steam_root`` of a combined suite, if set."""
    suite_path = Path(path).resolve()
    data = json.loads(suite_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        return None
    return _as_path(data.get("steam_root"))


def _config_from_dict(data: dict[str, Any], base_dir: Path) -> GameplayRunConfig:
    assertions = data.get("assertions", [])
    normalized_assertions: list[dict[str, Any]] = []
    for index, assertion in enumerate(assertions):
        if not isinstance(assertion, dict):
            continue
        _validate_assertion(assertion, index)
        normalized = dict(assertion)
        template = normalized.get("template")
        if isinstance(template, str) and template.strip() and not Path(template).is_absolute():
            normalized["template"] = str((base_dir / template).resolve())
        normalized_assertions.append(normalized)

    screenshot_value = data.get("screenshot_dir", "screenshots")
    screenshot_dir = (
        Path(screenshot_value) if isinstance(screenshot_value, str) else Path("screenshots")
    )
    if not screenshot_dir.is_absolute():
        screenshot_dir = (base_dir / screenshot_dir).resolve()

    steam_root = _as_path(data.get("steam_root"))
    if steam_root is not None and not steam_root.is_absolute():
        steam_root = (base_dir / steam_root).resolve()

    bot = data.get("bot", {})
    if bot is None:
        bot = {}
    if not isinstance(bot, dict):
        raise ValueError("'bot' must be an object.")
    bot_actions = bot.get("actions", [])
    if not isinstance(bot_actions, list) or any(
        not isinstance(action, dict) or not isinstance(action.get("action"), str)
        for action in bot_actions
    ):
        raise ValueError("'bot.actions' must be a list of action objects.")

    return GameplayRunConfig(
        timeout=float(data.get("timeout", 30.0)),
        executable_name=data.get("executable_name"),
        assertions=normalized_assertions,
        monitor_index=int(data.get("monitor_index", 0)),
        screenshot_dir=screenshot_dir,
        poll_interval=float(data.get("poll_interval", 0.5)),
        capture_delay=float(data.get("capture_delay", 0.0)),
        capture_poll_seconds=float(data.get("capture_poll_seconds", 0.0)),
        steam_root=steam_root,
        actions=_actions(data.get("actions", [])),
        bot_enabled=bool(bot.get("enabled", False)),
        bot_max_steps=int(bot.get("max_steps", 20)),
        bot_step_interval=float(bot.get("step_interval", 0.25)),
        bot_actions=[dict(action) for action in bot_actions],
    )


_KNOWN_CHECKS = {
    "frame_not_black",
    "template_match",
    "color_detected",
    "color_region_detected",
    "ocr_contains",
    "ocr_word_present",
    "ocr_region_contains",
}


def _validate_assertion(assertion: dict[str, Any], index: int) -> None:
    """Validate assertion config keys at load time; raise ValueError on errors."""
    if "name" not in assertion:
        raise ValueError(f"Assertion at index {index} is missing required 'name'.")
    check = assertion.get("check")
    if check not in _KNOWN_CHECKS:
        raise ValueError(
            f"Assertion {assertion.get('name', index)!r} has unsupported 'check': "
            f"{check!r}. Known: {sorted(_KNOWN_CHECKS)}"
        )
    if check == "template_match" and not isinstance(assertion.get("template"), str):
        raise ValueError(f"Assertion {assertion['name']!r} requires 'template' (path).")
    if check == "frame_not_black":
        try:
            brightness_threshold = int(assertion.get("brightness_threshold", 8))
            min_visible_ratio = float(assertion.get("min_visible_ratio", 0.02))
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"Assertion {assertion['name']!r} has invalid frame thresholds."
            ) from exc
        if not 0 <= brightness_threshold <= 255 or not 0.0 <= min_visible_ratio <= 1.0:
            raise ValueError(f"Assertion {assertion['name']!r} has out-of-range frame thresholds.")
    if check in {"color_detected", "color_region_detected"}:
        color = assertion.get("color")
        if not (
            isinstance(color, (list, tuple))
            and len(color) == 3
            and all(isinstance(c, int) for c in color)
        ):
            raise ValueError(f"Assertion {assertion['name']!r} requires 'color' as [b, g, r].")
    if check in {"color_region_detected", "ocr_region_contains"}:
        region = assertion.get("region")
        if not (
            isinstance(region, (list, tuple))
            and len(region) == 4
            and all(isinstance(c, int) for c in region)
        ):
            raise ValueError(f"Assertion {assertion['name']!r} requires 'region' as [x, y, w, h].")
    if check in {"ocr_contains", "ocr_word_present", "ocr_region_contains"}:
        if not isinstance(assertion.get("text"), str) or not assertion.get("text", "").strip():
            raise ValueError(f"Assertion {assertion['name']!r} requires 'text'.")
    if "confidence_threshold" in assertion:
        try:
            float(assertion["confidence_threshold"])
        except (TypeError, ValueError):
            raise ValueError(
                f"Assertion {assertion['name']!r} 'confidence_threshold' must be numeric."
            )
    _REGION_SUPPORTED = {
        "color_region_detected",
        "ocr_region_contains",
        "ocr_contains",
        "ocr_word_present",
    }
    if "region" in assertion and check not in _REGION_SUPPORTED:
        raise ValueError(f"Assertion {assertion['name']!r} ('{check}') does not support 'region'.")


def _actions(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise ValueError("'actions' must be a list.")
    actions: list[dict[str, Any]] = []
    for index, action in enumerate(value):
        if not isinstance(action, dict) or not isinstance(action.get("action"), str):
            raise ValueError(f"Action at index {index} must have a string 'action'.")
        actions.append(dict(action))
    return actions
