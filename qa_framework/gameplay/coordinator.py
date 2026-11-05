from __future__ import annotations

import json
from pathlib import Path

from qa_framework.adapters.local import local_game_from_executable
from qa_framework.adapters.steam import discover_games, find_game
from qa_framework.gameplay.report import GameplayReportGenerator
from qa_framework.gameplay.runner import GameplayRunConfig, GameplayRunResult, run_gameplay_suite
from qa_framework.gameplay.suite import (
    combined_steam_root,
    load_run_config,
)


def _effective_steam_root(
    override: Path | None,
    config: GameplayRunConfig,
) -> Path | None:
    return config.steam_root or override


def run_game_by_app_id(
    app_id: int,
    suite_path: str | Path,
    steam_root: Path | None = None,
    output_dir: Path = Path("reports"),
) -> GameplayRunResult:
    """Run the gameplay suite for a single Steam game identified by App ID."""
    config = load_run_config(suite_path)
    root = _effective_steam_root(steam_root, config)
    game = find_game(app_id, root)
    result = run_gameplay_suite(game, config)
    GameplayReportGenerator().generate([result], output_dir)
    return result


def run_local_game(
    executable: str | Path,
    suite_path: str | Path,
    *,
    name: str | None = None,
    output_dir: Path = Path("reports"),
) -> GameplayRunResult:
    """Run the same gameplay QA against any local game executable."""
    config = load_run_config(suite_path)
    game = local_game_from_executable(executable, name=name)
    result = run_gameplay_suite(game, config)
    GameplayReportGenerator().generate([result], output_dir)
    return result


def run_combined_suite(
    combined_path: str | Path,
    steam_root: Path | None = None,
    output_dir: Path = Path("reports"),
) -> list[GameplayRunResult]:
    """Run a combined suite that references per-game App IDs and suite files.

    Each entry in the top-level ``games`` array needs ``app_id`` and ``suite``
    (a path relative to the combined suite file). All runs share one HTML
    report. A top-level ``steam_root`` (or a per-entry one) overrides Steam
    library discovery without any code change.
    """
    combined = Path(combined_path).resolve()
    data = json.loads(combined.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Combined suite root must be a JSON object.")
    games = data.get("games")
    configured_root = data.get("steam_root")
    if steam_root is None and isinstance(configured_root, str) and configured_root.strip():
        steam_root = Path(configured_root)
    if not isinstance(games, list) or not games:
        raise ValueError("Combined suite 'games' must be a non-empty list.")

    base_dir = combined.parent
    combined_root = combined_steam_root(combined) or steam_root
    games_on_machine = {game.app_id: game for game in discover_games(combined_root)}

    results: list[GameplayRunResult] = []
    for index, entry in enumerate(games):
        if not isinstance(entry, dict):
            raise ValueError(f"Game entry at index {index} must be an object.")
        app_id = entry.get("app_id")
        suite_rel = entry.get("suite")
        if not isinstance(app_id, int) or not isinstance(suite_rel, str):
            raise ValueError(f"Game entry at index {index} needs 'app_id' and 'suite'.")
        suite_path = (base_dir / suite_rel).resolve()

        game = games_on_machine.get(app_id)
        if game is None:
            results.append(
                GameplayRunResult(
                    game_name=f"App {app_id}",
                    app_id=app_id,
                    install_path="not installed",
                    started=False,
                    startup_error="Game not found in installed Steam libraries.",
                    cleanup=None,
                    screenshot_path=None,
                    executable=None,
                    pid=None,
                )
            )
            continue

        config = load_run_config(suite_path)
        root = _effective_steam_root(combined_root, config)
        game = find_game(app_id, root)
        results.append(run_gameplay_suite(game, config))

    GameplayReportGenerator().generate(results, output_dir)
    return results
