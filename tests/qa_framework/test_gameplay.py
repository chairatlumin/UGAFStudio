from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import cv2
import numpy as np
import pytest

from app.vision.ocr import OCREngine
from qa_framework.adapters.steam import SteamGame
from qa_framework.gameplay.assertions import (
    AssertionResult,
    VisualAssertionEngine,
)
from qa_framework.gameplay.coordinator import run_combined_suite
from qa_framework.gameplay.launcher import (
    CleanupResult,
    LaunchedGame,
    launch_game,
    terminate_game,
)
from qa_framework.gameplay.report import GameplayReportGenerator
from qa_framework.gameplay.runner import (
    GameplayRunConfig,
    GameplayRunResult,
    _resolve_executable,
    run_gameplay_suite,
)
from qa_framework.gameplay.suite import load_run_config


@dataclass
class FakeProcess:
    """Minimal subprocess.Popen stand-in for launcher tests."""

    returncode: int | None = None
    pid: int = 4242
    _killed: bool = False

    def poll(self) -> int | None:
        return self.returncode

    def terminate(self) -> None:
        self.returncode = 0

    def kill(self) -> None:
        self.returncode = -9

    def wait(self, timeout: float | None = None) -> int:
        if self.returncode is None:
            self.returncode = 0
        return self.returncode


def _make_game(install_path: Path, app_id: int = 123) -> SteamGame:
    return SteamGame(
        app_id=app_id,
        name=f"Game {app_id}",
        install_path=install_path,
        manifest_path=install_path / "appmanifest.acf",
    )


def _fake_launcher(proc: FakeProcess) -> Callable[[Path, Path | None], Any]:
    def launcher(executable: Path, working_directory: Path | None) -> Any:
        return proc

    return launcher


def test_launch_game_polls_until_timeout_when_process_stays_alive(tmp_path: Path) -> None:
    proc = FakeProcess(returncode=None)
    started = time.monotonic()
    game = launch_game(
        tmp_path / "Game.exe",
        startup_timeout=0.2,
        poll_interval=0.05,
        launcher=_fake_launcher(proc),
    )
    elapsed = time.monotonic() - started

    assert game.exited_early is False
    assert game.startup_error is None
    assert elapsed >= 0.2


def test_launch_game_reports_failed_startup_when_process_exits_early(tmp_path: Path) -> None:
    proc = FakeProcess(returncode=1)
    game = launch_game(
        tmp_path / "Game.exe",
        startup_timeout=1.0,
        poll_interval=0.05,
        launcher=_fake_launcher(proc),
    )

    assert game.exited_early is True
    assert game.startup_error is not None
    assert "exited during startup" in game.startup_error


def test_launch_game_surfaces_oserror(tmp_path: Path) -> None:
    def failing_launcher(executable: Path, working_directory: Path | None) -> Any:
        raise OSError("boom")

    game = launch_game(
        tmp_path / "Game.exe",
        launcher=failing_launcher,
    )

    assert game.pid == -1
    assert game.process is None
    assert game.exited_early is True
    assert game.startup_error is not None
    assert "boom" in game.startup_error


def test_terminate_game_cleans_alive_process(tmp_path: Path) -> None:
    proc = FakeProcess(returncode=None)
    game = LaunchedGame(pid=999, process=proc, exited_early=False, startup_error=None)  # type: ignore[arg-type]

    result = terminate_game(game)

    assert isinstance(result, CleanupResult)
    assert result.cleaned is True
    assert result.status == "terminated"
    assert proc.returncode is not None


def test_terminate_game_handles_already_exited(tmp_path: Path) -> None:
    proc = FakeProcess(returncode=0)
    game = LaunchedGame(pid=999, process=proc, exited_early=True, startup_error="x")  # type: ignore[arg-type]

    result = terminate_game(game)

    assert result.cleaned is True
    assert result.status == "already_exited"


def test_terminate_game_safe_without_process(tmp_path: Path) -> None:
    game = LaunchedGame(pid=-1, process=None, exited_early=True, startup_error="x")

    result = terminate_game(game)

    assert result.cleaned is False
    assert result.status == "no_process"


def test_visual_assertion_template_match_uses_temp_image(tmp_path: Path) -> None:
    template = np.zeros((10, 10, 3), dtype=np.uint8)
    template[:5, :5] = (255, 255, 255)
    frame = np.zeros((40, 40, 3), dtype=np.uint8)
    frame[10:20, 10:20] = (255, 255, 255)

    template_path = tmp_path / "tpl.png"
    cv2.imwrite(str(template_path), template)

    engine = VisualAssertionEngine()
    results = engine.assert_frame(
        frame,
        [
            {
                "name": "logo",
                "check": "template_match",
                "template": str(template_path),
                "threshold": 0.8,
            }
        ],
    )

    assert len(results) == 1
    assert results[0].passed is True


def test_visual_assertion_color_detected(tmp_path: Path) -> None:
    frame = np.zeros((20, 20, 3), dtype=np.uint8)
    frame[5:10, 5:10] = (200, 100, 50)

    engine = VisualAssertionEngine()
    results = engine.assert_frame(
        frame,
        [{"name": "accent", "check": "color_detected", "color": [200, 100, 50], "tolerance": 30}],
    )

    assert results[0].passed is True


def test_visual_assertion_ocr_unavailable_reports_failure() -> None:
    frame = np.zeros((20, 20, 3), dtype=np.uint8)
    engine = VisualAssertionEngine(ocr_engine=OCREngine(tesseract_cmd="Z:/nope/tesseract.exe"))
    results = engine.assert_frame(
        frame,
        [{"name": "text", "check": "ocr_contains", "text": "Play"}],
    )
    assert results[0].passed is False
    assert "OCR unavailable" in results[0].message


def test_runner_launches_captures_asserts_and_cleans_up(tmp_path: Path) -> None:
    exe = tmp_path / "Game.exe"
    exe.write_bytes(b"MZ")
    game = _make_game(tmp_path, app_id=4077460)

    proc = FakeProcess(returncode=None)
    frame = np.zeros((20, 20, 3), dtype=np.uint8)
    frame[5:10, 5:10] = (200, 100, 50)

    class FakeCapture:
        def set_monitor(self, index: int) -> None:
            pass

        def capture(self) -> np.ndarray:
            return frame

    class FakeScreenshot:
        def __init__(self) -> None:
            self.saved: list[np.ndarray] = []

        def save(self, f: np.ndarray, name: str | None = None) -> Path:
            self.saved.append(f)
            return tmp_path / f"shot_{name}.png"

    config = GameplayRunConfig(
        timeout=0.2,
        assertions=[
            {
                "name": "accent",
                "check": "color_detected",
                "color": [200, 100, 50],
                "tolerance": 30,
            }
        ],
        screenshot_dir=tmp_path,
    )

    result = run_gameplay_suite(
        game,
        config,
        capture_service=FakeCapture(),  # type: ignore[arg-type]
        screenshot_service=FakeScreenshot(),  # type: ignore[arg-type]
        launcher=_fake_launcher(proc),
    )

    assert result.started is True
    assert result.screenshot_path is not None
    assert len(result.assertions) == 1
    assert result.assertions[0].passed is True
    assert result.cleanup is not None
    assert result.cleanup.status == "terminated"
    assert proc.returncode is not None  # cleaned up


def test_runner_failed_startup_still_cleans_up_and_reports_failure(tmp_path: Path) -> None:
    exe = tmp_path / "Game.exe"
    exe.write_bytes(b"MZ")
    game = _make_game(tmp_path, app_id=99)

    proc = FakeProcess(returncode=1)
    config = GameplayRunConfig(timeout=0.2, assertions=[])

    result = run_gameplay_suite(
        game,
        config,
        launcher=_fake_launcher(proc),
    )

    assert result.started is False
    assert result.startup_error is not None
    assert result.passed is False
    assert result.cleanup is not None
    assert result.cleanup.status == "already_exited"


def test_runner_missing_executable_reports_failure(tmp_path: Path) -> None:
    game = _make_game(tmp_path, app_id=7)
    config = GameplayRunConfig(timeout=0.2, assertions=[])

    result = run_gameplay_suite(game, config)

    assert result.started is False
    assert result.startup_error is not None
    assert "No executable" in result.startup_error
    assert result.cleanup is None


def test_gameplay_report_includes_required_fields(tmp_path: Path) -> None:
    run = GameplayRunResult(
        game_name="Demo Game",
        app_id=4077460,
        install_path=str(tmp_path / "install"),
        started=True,
        startup_error=None,
        cleanup=CleanupResult(cleaned=True, status="terminated", note="ok"),
        screenshot_path=tmp_path / "shot.png",
        assertions=[AssertionResult(name="accent", passed=True, message="found")],
        duration_ms=123.4,
    )
    run.report_path = tmp_path / "gameplay_report.html"

    html = GameplayReportGenerator().to_html([run])

    assert "Demo Game" in html
    assert "4077460" in html
    assert str(run.install_path) in html
    assert "terminated" in html
    assert str(run.report_path) in html
    assert "123.4" in html


def test_load_run_config_reads_assertions(tmp_path: Path) -> None:
    suite = tmp_path / "suite.json"
    suite.write_text(
        json.dumps(
            {
                "timeout": 15.0,
                "assertions": [{"name": "x", "check": "color_detected", "color": [1, 2, 3]}],
            }
        ),
        encoding="utf-8",
    )

    config = load_run_config(suite)

    assert config.timeout == 15.0
    assert config.assertions[0]["check"] == "color_detected"


def test_default_launcher_uses_devnull_no_backpressure() -> None:
    import sys

    from qa_framework.gameplay.launcher import _default_launcher

    # Unit check: the production launcher must not attach pipes to game
    # stdout/stderr, so a chatty game cannot block on a full pipe buffer we
    # never drain. DEVNULL yields None handles (a PIPE would be a reader).
    proc = _default_launcher(Path(sys.executable), None)
    try:
        assert proc.stdout is None
        assert proc.stderr is None
    finally:
        proc.kill()


def test_launch_game_no_backpressure_under_flood(tmp_path: Path) -> None:
    import subprocess
    import sys

    # A process that floods stdout would block a PIPE-backed Popen; a DEVNULL
    # launcher must let it run and exit without freezing the caller.
    flood = (
        "import sys\n"
        "for _ in range(200000):\n"
        "    sys.stdout.write('x' * 1000 + '\\n')\n"
        "    sys.stderr.write('y' * 1000 + '\\n')\n"
    )
    script = tmp_path / "flood.py"
    script.write_text(flood, encoding="utf-8")

    def flood_launcher(executable: Path, working_directory: Path | None) -> Any:
        return subprocess.Popen(
            [sys.executable, str(script)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    started = time.monotonic()
    game = launch_game(
        script,
        startup_timeout=15.0,
        poll_interval=0.05,
        launcher=flood_launcher,
    )
    elapsed = time.monotonic() - started

    assert game.exited_early is True  # it exited on its own quickly
    assert elapsed < 15.0  # never blocked waiting on pipe buffer
    cleanup = terminate_game(game)
    assert cleanup.status in {"already_exited", "terminated"}


def test_resolve_executable_recursive_single(tmp_path: Path) -> None:
    game = _make_game(tmp_path)
    (tmp_path / "bin").mkdir()
    exe = tmp_path / "bin" / "Game.exe"
    exe.write_bytes(b"MZ")

    config = GameplayRunConfig(timeout=0.2, assertions=[])
    resolution = _resolve_executable(game, config)

    assert resolution.executable == exe
    assert resolution.candidates == [exe]


def test_resolve_executable_recursive_ambiguous_reports_candidates(tmp_path: Path) -> None:
    game = _make_game(tmp_path)
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    (tmp_path / "a" / "Game.exe").write_bytes(b"MZ")
    (tmp_path / "b" / "Launcher.exe").write_bytes(b"MZ")

    config = GameplayRunConfig(timeout=0.2, assertions=[])
    resolution = _resolve_executable(game, config)

    assert resolution.executable is None
    assert len(resolution.candidates) == 2


def test_resolve_executable_by_name_recursive(tmp_path: Path) -> None:
    game = _make_game(tmp_path)
    (tmp_path / "deep").mkdir()
    exe = tmp_path / "deep" / "Game.exe"
    exe.write_bytes(b"MZ")

    config = GameplayRunConfig(timeout=0.2, assertions=[], executable_name="Game.exe")
    resolution = _resolve_executable(game, config)

    assert resolution.executable == exe


def test_runner_reports_exact_executable_and_pid(tmp_path: Path) -> None:
    exe = tmp_path / "Game.exe"
    exe.write_bytes(b"MZ")
    game = _make_game(tmp_path, app_id=4077460)

    proc = FakeProcess(returncode=None)
    frame = np.zeros((20, 20, 3), dtype=np.uint8)
    frame[5:10, 5:10] = (200, 100, 50)

    class FakeCapture:
        def set_monitor(self, index: int) -> None:
            pass

        def capture(self) -> np.ndarray:
            return frame

    config = GameplayRunConfig(
        timeout=0.2,
        assertions=[],
        screenshot_dir=tmp_path,
    )

    result = run_gameplay_suite(
        game,
        config,
        capture_service=FakeCapture(),  # type: ignore[arg-type]
        launcher=_fake_launcher(proc),
    )

    assert result.executable == exe
    assert result.pid == proc.pid
    html = GameplayReportGenerator().to_html([result])
    assert str(exe) in html
    assert str(proc.pid) in html


def test_steam_root_propagates_through_combined(tmp_path: Path) -> None:
    # Verify the combined loader reads a top-level steam_root without code change.
    combined = tmp_path / "combined.json"
    combined.write_text(
        json.dumps(
            {
                "steam_root": str(tmp_path / "custom_steam"),
                "games": [
                    {"app_id": 4077460, "suite": "game.json"},
                ],
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "game.json").write_text(
        json.dumps({"timeout": 5.0, "assertions": []}), encoding="utf-8"
    )

    # No real Steam at the custom root -> game reported as not installed,
    # proving steam_root was applied (no crash, cleanup-safe path).
    results = run_combined_suite(combined, output_dir=tmp_path)
    assert len(results) == 1
    assert results[0].started is False
    assert results[0].startup_error is not None
    assert "not found in installed Steam libraries" in results[0].startup_error
    assert results[0].report_path is not None
    assert Path(results[0].report_path).exists()


def test_gameplay_report_includes_executable_and_pid(tmp_path: Path) -> None:
    exe = tmp_path / "Game.exe"
    run = GameplayRunResult(
        game_name="Demo Game",
        app_id=4077460,
        install_path=str(tmp_path / "install"),
        started=True,
        startup_error=None,
        cleanup=CleanupResult(cleaned=True, status="terminated", note="ok"),
        screenshot_path=tmp_path / "shot.png",
        assertions=[AssertionResult(name="accent", passed=True, message="found")],
        duration_ms=123.4,
        executable=exe,
        pid=555,
    )
    run.report_path = tmp_path / "gameplay_report.html"

    html = GameplayReportGenerator().to_html([run])

    assert "Demo Game" in html
    assert "4077460" in html
    assert str(run.install_path) in html
    assert "terminated" in html
    assert str(run.report_path) in html
    assert "123.4" in html
    assert str(exe) in html
    assert "555" in html


def test_terminate_game_kills_process_tree(tmp_path: Path) -> None:
    import subprocess
    import sys

    # Parent python process spawns a child that sleeps; terminating only the
    # parent must also kill the child so nothing is left running after QA.
    parent = (
        "import subprocess, sys\n"
        "subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])\n"
        "import time\n"
        "time.sleep(60)\n"
    )
    script = tmp_path / "parent.py"
    script.write_text(parent, encoding="utf-8")

    def py_launcher(executable: Path, working_directory: Path | None) -> Any:
        return subprocess.Popen(
            [sys.executable, str(script)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    game = launch_game(
        script,
        startup_timeout=5.0,
        poll_interval=0.2,
        launcher=py_launcher,
    )
    assert game.exited_early is False

    result = terminate_game(game)
    assert result.status == "terminated"

    # Ensure no lingering child sleeper leaked from this test.
    out = subprocess.run(
        ["tasklist", "/FI", "IMAGENAME eq python.exe", "/NH"],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        check=False,
    )
    assert "time.sleep(60)" not in out.stdout


def test_load_run_config_resolves_paths_relative_to_suite_file(tmp_path: Path) -> None:
    suite_dir = tmp_path / "suites"
    assets = suite_dir / "assets"
    assets.mkdir(parents=True)
    template = assets / "menu.png"
    template.write_bytes(b"template")
    suite_file = suite_dir / "game.json"
    suite_file.write_text(
        json.dumps(
            {
                "screenshot_dir": "evidence",
                "assertions": [
                    {"name": "menu", "check": "template_match", "template": "assets/menu.png"}
                ],
            }
        ),
        encoding="utf-8",
    )

    config = load_run_config(suite_file)

    assert config.screenshot_dir == (suite_dir / "evidence").resolve()
    assert config.assertions[0]["template"] == str(template.resolve())


# --- NEXT_SPRINT: runner executes ocr/color_region assertions + suite validation ---


def test_load_run_config_validates_new_assertion_keys(tmp_path: Path) -> None:
    suite = tmp_path / "bad.json"
    suite.write_text(
        json.dumps(
            {"assertions": [{"name": "x", "check": "color_region_detected", "color": [1, 2, 3]}]}
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="region"):
        load_run_config(suite)


def test_load_run_config_rejects_unknown_check(tmp_path: Path) -> None:
    suite = tmp_path / "bad.json"
    suite.write_text(
        json.dumps({"assertions": [{"name": "x", "check": "nope"}]}),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="unsupported"):
        load_run_config(suite)


def test_runner_executes_ocr_assertions(tmp_path: Path) -> None:
    exe = tmp_path / "Game.exe"
    exe.write_bytes(b"MZ")
    game = _make_game(tmp_path, app_id=4077460)

    proc = FakeProcess(returncode=None)
    frame = np.zeros((20, 20, 3), dtype=np.uint8)

    class FakeCapture:
        def set_monitor(self, index: int) -> None:
            pass

        def capture(self) -> np.ndarray:
            return frame

    class StubOCR:
        def available(self) -> bool:
            return True

        def read(
            self,
            f: np.ndarray,
            *,
            scale: float = 1.0,
            psm: int | None = None,
            lang: str = "eng",
            config: str = "",
            region: tuple[int, int, int, int] | None = None,
            preprocessing: str | None = None,
        ) -> str:
            return "PLAY"

        def read_words(
            self,
            f: np.ndarray,
            *,
            scale: float = 1.0,
            lang: str = "eng",
            config: str = "",
            psm: int | None = None,
            region: tuple[int, int, int, int] | None = None,
            preprocessing: str | None = None,
            confidence_threshold: float = 0.0,
        ) -> list:
            from app.vision.ocr import OCRWord
            from app.vision.template_match import MatchResult

            return [
                OCRWord(
                    text="PLAY",
                    box=MatchResult(x=1, y=1, width=10, height=5, confidence=0.9),
                    confidence=0.9,
                )
            ]

    config = GameplayRunConfig(
        timeout=0.2,
        assertions=[
            {"name": "title", "check": "ocr_contains", "text": "play"},
            {
                "name": "play btn",
                "check": "ocr_word_present",
                "text": "PLAY",
                "confidence_threshold": 0.6,
            },
        ],
        screenshot_dir=tmp_path,
    )

    result = run_gameplay_suite(
        game,
        config,
        capture_service=FakeCapture(),  # type: ignore[arg-type]
        assertion_engine=VisualAssertionEngine(ocr_engine=StubOCR()),  # type: ignore[arg-type]
        launcher=_fake_launcher(proc),
    )

    assert result.started is True
    assert len(result.assertions) == 2
    assert all(a.passed for a in result.assertions)
    assert result.cleanup.status == "terminated"


def test_runner_executes_color_region_assertions(tmp_path: Path) -> None:
    exe = tmp_path / "Game.exe"
    exe.write_bytes(b"MZ")
    game = _make_game(tmp_path, app_id=4511140)

    proc = FakeProcess(returncode=None)
    frame = np.zeros((100, 100, 3), dtype=np.uint8)
    frame[10:20, 10:20] = (30, 30, 200)  # red region

    class FakeCapture:
        def set_monitor(self, index: int) -> None:
            pass

        def capture(self) -> np.ndarray:
            return frame

    config = GameplayRunConfig(
        timeout=0.2,
        assertions=[
            {
                "name": "health",
                "check": "color_region_detected",
                "color": [30, 30, 200],
                "region": [5, 5, 30, 30],
                "tolerance": 40,
            }
        ],
        screenshot_dir=tmp_path,
    )

    result = run_gameplay_suite(
        game,
        config,
        capture_service=FakeCapture(),  # type: ignore[arg-type]
        launcher=_fake_launcher(proc),
    )

    assert result.started is True
    assert result.assertions[0].passed is True
    assert result.cleanup.status == "terminated"


def test_capture_poll_retries_until_assertions_pass(tmp_path: Path) -> None:
    exe = tmp_path / "Game.exe"
    exe.write_bytes(b"MZ")
    game = _make_game(tmp_path, app_id=4077460)

    proc = FakeProcess(returncode=None)
    black = np.zeros((20, 20, 3), dtype=np.uint8)
    red = np.zeros((20, 20, 3), dtype=np.uint8)
    red[:] = (30, 30, 200)
    frames = [black, black, red]
    calls: list[int] = []

    class FakeCapture:
        def set_monitor(self, index: int) -> None:
            pass

        def capture(self) -> np.ndarray:
            calls.append(1)
            return frames[min(len(calls) - 1, len(frames) - 1)]

    config = GameplayRunConfig(
        timeout=0.2,
        capture_delay=0.0,
        capture_poll_seconds=5.0,
        poll_interval=0.05,
        assertions=[
            {
                "name": "red frame",
                "check": "color_detected",
                "color": [30, 30, 200],
                "tolerance": 20,
            }
        ],
        screenshot_dir=tmp_path,
    )

    result = run_gameplay_suite(
        game,
        config,
        capture_service=FakeCapture(),  # type: ignore[arg-type]
        launcher=_fake_launcher(proc),
    )

    assert result.started is True
    assert result.passed is True
    assert len(calls) == 3
    assert result.cleanup.status == "terminated"
    assert result.screenshot_path is not None
    saved = cv2.imread(str(result.screenshot_path))
    assert saved is not None
    assert (saved == red).all()


def test_capture_poll_budget_exhaustion_uses_last_frame(tmp_path: Path) -> None:
    exe = tmp_path / "Game.exe"
    exe.write_bytes(b"MZ")
    game = _make_game(tmp_path, app_id=4307180)

    proc = FakeProcess(returncode=None)
    calls: list[int] = []

    class FakeCapture:
        def set_monitor(self, index: int) -> None:
            pass

        def capture(self) -> np.ndarray:
            calls.append(1)
            return np.zeros((20, 20, 3), dtype=np.uint8)

    config = GameplayRunConfig(
        timeout=0.2,
        capture_poll_seconds=0.15,
        poll_interval=0.05,
        assertions=[
            {
                "name": "red frame",
                "check": "color_detected",
                "color": [30, 30, 200],
                "tolerance": 20,
            }
        ],
        screenshot_dir=tmp_path,
    )

    result = run_gameplay_suite(
        game,
        config,
        capture_service=FakeCapture(),  # type: ignore[arg-type]
        launcher=_fake_launcher(proc),
    )

    assert result.started is True
    assert result.passed is False
    assert len(calls) >= 2
    assert result.assertions[0].passed is False
    assert result.cleanup.status == "terminated"


def test_load_run_config_reads_capture_poll_seconds(tmp_path: Path) -> None:
    suite = tmp_path / "suite.json"
    suite.write_text(
        json.dumps({"timeout": 45.0, "capture_poll_seconds": 12.5, "assertions": []}),
        encoding="utf-8",
    )

    config = load_run_config(suite)

    assert config.capture_poll_seconds == 12.5
    assert config.timeout == 45.0


def test_load_run_config_capture_poll_seconds_defaults_to_zero(tmp_path: Path) -> None:
    suite = tmp_path / "suite.json"
    suite.write_text(json.dumps({"timeout": 45.0}), encoding="utf-8")

    config = load_run_config(suite)

    assert config.capture_poll_seconds == 0.0
