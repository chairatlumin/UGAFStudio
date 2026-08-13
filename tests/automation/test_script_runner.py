from __future__ import annotations

from pathlib import Path

from app.automation.script_runner import ScriptRunner
from app.vision.detector import ObjectDetector


def make_runner() -> ScriptRunner:
    mouse = type("Mouse", (), {"move": lambda self, x, y: None})()
    keyboard = type("Keyboard", (), {"press": lambda self, key: None})()
    return ScriptRunner(
        mouse=mouse,
        keyboard=keyboard,
        vision=ObjectDetector(),
        logger=None,
    )


def test_run_exposes_context_objects() -> None:
    runner = make_runner()

    script = "result = mouse is not None and keyboard is not None and vision is not None"
    namespace = runner.run(script)

    assert namespace["result"] is True


def test_run_executes_user_logic() -> None:
    runner = make_runner()

    namespace = runner.run("answer = 6 * 7")

    assert namespace["answer"] == 42


def test_run_file(tmp_path: Path) -> None:
    script = tmp_path / "test_script.py"
    script.write_text("value = 'ok'", encoding="utf-8")

    runner = make_runner()

    namespace = runner.run_file(script)

    assert namespace["value"] == "ok"
