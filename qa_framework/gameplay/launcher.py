from __future__ import annotations

import os
import signal
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import psutil

GameLauncher = Callable[[Path, Path | None], "subprocess.Popen[Any]"]


@dataclass(frozen=True)
class LaunchedGame:
    """Handle to a launched game process."""

    pid: int
    process: subprocess.Popen[Any] | None
    exited_early: bool
    startup_error: str | None
    executable: Path | None = None
    descendant_pids: tuple[int, ...] = ()


@dataclass(frozen=True)
class CleanupResult:
    """Outcome of terminating a launched game process."""

    cleaned: bool
    status: str
    note: str | None = None


def _default_launcher(
    executable: Path,
    working_directory: Path | None,
) -> subprocess.Popen[Any]:
    cwd = working_directory or executable.parent
    return subprocess.Popen(
        [str(executable)],
        cwd=str(cwd),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _descendant_pids(pid: int) -> set[int]:
    """Return current descendants so short-lived wrappers cannot leak children."""
    if pid <= 0:
        return set()
    try:
        return {child.pid for child in psutil.Process(pid).children(recursive=True)}
    except (psutil.Error, OSError):
        return set()


def launch_game(
    executable: Path,
    *,
    startup_timeout: float = 30.0,
    poll_interval: float = 0.5,
    working_directory: Path | None = None,
    launcher: GameLauncher | None = None,
) -> LaunchedGame:
    """Launch a game and wait for it to reach a running state.

    Child PIDs are sampled while the launcher is alive. This matters for games
    that use a short-lived bootstrap executable and then spawn a Shipping
    executable that remains alive after the bootstrap exits.
    """
    spawn = launcher or _default_launcher

    try:
        process = spawn(executable, working_directory)
    except OSError as exc:
        return LaunchedGame(
            pid=-1,
            process=None,
            exited_early=True,
            startup_error=f"Failed to launch {executable}: {exc}",
            executable=executable,
        )

    deadline = time.monotonic() + max(0.0, startup_timeout)
    exited_early = False
    startup_error: str | None = None
    descendant_pids: set[int] = set()

    while time.monotonic() < deadline:
        descendant_pids.update(_descendant_pids(process.pid))
        if process.poll() is not None:
            exited_early = True
            code = process.returncode
            startup_error = f"Game process exited during startup (code {code})."
            break
        time.sleep(poll_interval)

    return LaunchedGame(
        pid=process.pid,
        process=process,
        exited_early=exited_early,
        startup_error=startup_error,
        executable=executable,
        descendant_pids=tuple(sorted(descendant_pids)),
    )


def _kill_process_tree(pid: int, descendant_pids: tuple[int, ...] = ()) -> None:
    """Kill a process and tracked descendants, including an exited wrapper."""
    pids = set(descendant_pids)
    if pid > 0:
        pids.add(pid)

    if os.name == "nt":
        for target in sorted(pids, reverse=True):
            subprocess.run(
                ["taskkill", "/T", "/F", "/PID", str(target)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
        return

    for target in sorted(pids, reverse=True):
        try:
            os.kill(target, getattr(signal, "SIGKILL", 9))
        except OSError:
            pass


def terminate_game(game: LaunchedGame) -> CleanupResult:
    """Terminate the game and all tracked descendants without leaving leaks."""
    process = game.process
    if process is None:
        return CleanupResult(
            cleaned=False,
            status="no_process",
            note="Nothing to terminate.",
        )

    if process.poll() is not None:
        _kill_process_tree(game.pid, game.descendant_pids)
        return CleanupResult(
            cleaned=True,
            status="already_exited",
            note=f"Process exited on its own (code {process.returncode}).",
        )

    try:
        process.terminate()
        try:
            process.wait(timeout=5.0)
        except subprocess.TimeoutExpired:
            _kill_process_tree(process.pid, game.descendant_pids)
        else:
            _kill_process_tree(process.pid, game.descendant_pids)
    except OSError as exc:
        return CleanupResult(
            cleaned=False,
            status="terminate_failed",
            note=str(exc),
        )

    return CleanupResult(cleaned=True, status="terminated")
