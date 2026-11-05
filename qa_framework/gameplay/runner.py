from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.capture.capture_service import CaptureService
from app.capture.screenshot_service import ScreenshotService
from qa_framework.adapters.local import LocalGame
from qa_framework.adapters.steam import SteamGame
from qa_framework.gameplay.assertions import (
    AssertionResult,
    VisualAssertionEngine,
)
from qa_framework.gameplay.bot import BotRunSummary, run_bot_episode
from qa_framework.gameplay.interaction import (
    InputController,
    WindowsInputController,
    execute_actions,
)
from qa_framework.gameplay.launcher import (
    CleanupResult,
    GameLauncher,
    launch_game,
    terminate_game,
)
from qa_framework.gameplay_agent.actions import Action
from qa_framework.gameplay_agent.base import GameplayAgent
from qa_framework.gameplay_agent.random_agent import RandomAgent


@dataclass
class GameplayRunResult:
    """Aggregated outcome of a gameplay QA run for a single Steam game."""

    game_name: str
    app_id: int | str
    install_path: str
    started: bool
    startup_error: str | None
    cleanup: CleanupResult | None
    screenshot_path: Path | None
    assertions: list[AssertionResult] = field(default_factory=list)
    duration_ms: float = 0.0
    report_path: Path | None = None
    executable: Path | None = None
    pid: int | None = None
    bot: BotRunSummary | None = None

    @property
    def passed(self) -> bool:
        if not self.started:
            return False
        if self.bot is not None and not self.bot.passed:
            return False
        return all(assertion.passed for assertion in self.assertions)


@dataclass
class _ExecutableResolution:
    """Result of locating a game executable under its install path."""

    executable: Path | None
    candidates: list[Path]


@dataclass
class GameplayRunConfig:
    """Declarative configuration for a gameplay run, sourced from JSON."""

    timeout: float = 30.0
    executable_name: str | None = None
    assertions: list[dict[str, Any]] = field(default_factory=list)
    monitor_index: int = 0
    screenshot_dir: Path = Path("screenshots")
    poll_interval: float = 0.5
    capture_delay: float = 0.0
    capture_poll_seconds: float = 0.0
    steam_root: Path | None = None
    actions: list[dict[str, Any]] = field(default_factory=list)
    bot_enabled: bool = False
    bot_max_steps: int = 20
    bot_step_interval: float = 0.25
    bot_actions: list[dict[str, Any]] = field(default_factory=list)


def run_gameplay_suite(
    game: SteamGame | LocalGame,
    config: GameplayRunConfig,
    *,
    capture_service: CaptureService | None = None,
    screenshot_service: ScreenshotService | None = None,
    assertion_engine: VisualAssertionEngine | None = None,
    launcher: GameLauncher | None = None,
    input_controller: InputController | None = None,
    gameplay_agent: GameplayAgent | None = None,
) -> GameplayRunResult:
    """Launch a Steam game, capture a frame, run visual assertions, and clean up.

    The process started for the game is always terminated, including on launch
    failure or assertion errors, so a game process is never left running.
    """
    started = time.perf_counter()

    resolution = _resolve_executable(game, config)
    executable = resolution.executable
    if executable is None:
        hint = (
            "; candidates found: " + ", ".join(str(p) for p in resolution.candidates)
            if resolution.candidates
            else ""
        )
        return GameplayRunResult(
            game_name=game.name,
            app_id=game.app_id,
            install_path=str(game.install_path),
            started=False,
            startup_error=(f"No executable found in {game.install_path} (recursive search).{hint}"),
            cleanup=None,
            screenshot_path=None,
            executable=None,
            pid=None,
        )

    launched = launch_game(
        executable,
        startup_timeout=config.timeout,
        poll_interval=config.poll_interval,
        launcher=launcher,
    )

    result = GameplayRunResult(
        game_name=game.name,
        app_id=game.app_id,
        install_path=str(game.install_path),
        started=not launched.exited_early,
        startup_error=launched.startup_error,
        cleanup=None,
        screenshot_path=None,
        executable=executable,
        pid=launched.pid,
    )

    try:
        if not launched.exited_early:
            if config.capture_delay > 0:
                time.sleep(config.capture_delay)
            captures = capture_service or CaptureService()
            captures.set_monitor(config.monitor_index)
            screenshots = screenshot_service or ScreenshotService(config.screenshot_dir)
            engine = assertion_engine or VisualAssertionEngine()

            if config.actions:
                controller = input_controller or WindowsInputController(launched.pid)
                execute_actions(
                    config.actions,
                    controller,
                    capture=captures.capture,
                    assert_frame=engine.assert_frame,
                )

            if config.bot_enabled:
                controller = input_controller or WindowsInputController(launched.pid)
                agent = gameplay_agent or RandomAgent(
                    actions=[
                        Action(
                            action=str(item["action"]),
                            params={key: value for key, value in item.items() if key != "action"},
                        )
                        for item in config.bot_actions
                    ]
                )
                if not config.bot_actions and gameplay_agent is None:
                    raise ValueError(
                        "bot_enabled requires bot.actions or an injected gameplay_agent."
                    )
                result.bot = run_bot_episode(
                    agent,
                    captures.capture,
                    controller,
                    max_steps=config.bot_max_steps,
                    step_interval=config.bot_step_interval,
                )

            frame, assertions = _capture_until_pass(captures, engine, config.assertions, config)
            result.screenshot_path = screenshots.save(frame, name=f"qa_{game.app_id}")
            result.assertions = assertions
    finally:
        result.cleanup = terminate_game(launched)

    result.duration_ms = (time.perf_counter() - started) * 1000.0
    return result


def _capture_until_pass(
    captures: CaptureService,
    engine: VisualAssertionEngine,
    assertions: list[dict[str, Any]],
    config: GameplayRunConfig,
) -> tuple[Any, list[AssertionResult]]:
    """Capture frames until every assertion passes or the poll budget ends.

    With ``capture_poll_seconds == 0`` this captures and asserts exactly once
    (previous behaviour). With a positive budget it re-captures every
    ``poll_interval`` seconds until all assertions pass, so nondeterministic
    startup states (intro videos, loading screens) do not fail the run; the
    last frame/assertions stand when the budget is exhausted.
    """
    deadline = time.monotonic() + max(0.0, config.capture_poll_seconds)
    while True:
        frame = captures.capture()
        results = engine.assert_frame(frame, assertions)
        if all(result.passed for result in results) or time.monotonic() >= deadline:
            return frame, results
        time.sleep(max(config.poll_interval, 0.1))


def _resolve_executable(
    game: SteamGame | LocalGame,
    config: GameplayRunConfig,
) -> _ExecutableResolution:
    """Locate the game executable, searching recursively below the install root.

    When ``executable_name`` is set it is resolved relative to the install root
    (recursively); otherwise every ``*.exe`` under the install root is
    considered. If exactly one candidate exists it is used; otherwise (zero or
    many) the resolution is ambiguous and ``executable`` is ``None`` so the
    caller can report actionable paths.
    """
    install = game.install_path
    if config.executable_name:
        matches = sorted(install.rglob(config.executable_name))
        matches = [p for p in matches if p.is_file()]
        return _ExecutableResolution(
            executable=matches[0] if len(matches) == 1 else None,
            candidates=matches,
        )

    candidates = sorted(install.rglob("*.exe"))
    if len(candidates) == 1:
        return _ExecutableResolution(executable=candidates[0], candidates=candidates)
    return _ExecutableResolution(executable=None, candidates=candidates)
