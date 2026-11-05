from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest

from qa_framework.robot.library import UGAFKeywords


class FakeCapture:
    def __init__(self, frame: np.ndarray | None = None) -> None:
        self.frame = frame if frame is not None else np.full((8, 8, 4), 255, dtype=np.uint8)
        self.index: int | None = None

    def capture(self) -> np.ndarray:
        return self.frame

    def all_monitors(self) -> list[object]:
        return [object(), object()]

    def set_monitor(self, index: int) -> None:
        self.index = index

    def current_monitor(self) -> SimpleNamespace:
        return SimpleNamespace(left=0, top=0)


class FakeMouse:
    def __init__(self) -> None:
        self.clicked: tuple[int, int, str] | None = None

    def click(self, x: int, y: int, button: str = "left") -> None:
        self.clicked = (x, y, button)


class FakeKeyboard:
    def __init__(self) -> None:
        self.pressed: list[str] = []
        self.typed: list[tuple[str, float]] = []

    def press(self, key: str) -> None:
        self.pressed.append(key)

    def write(self, text: str, interval: float = 0.0) -> None:
        self.typed.append((text, interval))


class FakeOCR:
    def available(self) -> bool:
        return True

    def read(self, frame: np.ndarray, *, lang: str = "eng") -> str:
        del frame, lang
        return "Main Menu"


def make_library(tmp_path: Path, frame: np.ndarray | None = None) -> UGAFKeywords:
    return UGAFKeywords(
        output_dir=tmp_path,
        capture=FakeCapture(frame),  # type: ignore[arg-type]
        mouse=FakeMouse(),  # type: ignore[arg-type]
        keyboard=FakeKeyboard(),  # type: ignore[arg-type]
        ocr=FakeOCR(),  # type: ignore[arg-type]
        focus_checker=lambda title: title == "Test Game",
    )


def test_input_keywords_are_locked_until_explicit_enable(tmp_path: Path) -> None:
    library = make_library(tmp_path)
    with pytest.raises(RuntimeError, match="input is disabled"):
        library.click_at(10, 20)
    with pytest.raises(RuntimeError, match="input is disabled"):
        library.press_key("enter")

    library.enable_game_input("Test Game")
    library.click_at(10, 20, "RIGHT")
    library.press_key("enter")
    library.type_text("hello", 0.1)

    assert library._mouse.clicked == (10, 20, "right")
    assert library._keyboard.pressed == ["enter"]
    assert library._keyboard.typed == [("hello", 0.1)]


def test_screen_assertions_and_screenshot_write_evidence(tmp_path: Path) -> None:
    library = make_library(tmp_path)
    library.capture_screen()
    library.frame_should_not_be_black()
    library.text_should_be_visible("menu")
    saved = Path(library.save_screenshot("main menu/loaded"))

    assert saved.parent == tmp_path
    assert saved.is_file()
    assert saved.suffix == ".png"
    assert "_" in saved.stem


def test_wait_for_text_returns_saved_evidence(tmp_path: Path) -> None:
    library = make_library(tmp_path)
    evidence = Path(library.wait_for_text("main menu", timeout=0, interval=0.01))

    assert evidence.is_file()
    assert evidence.parent == tmp_path


def test_monitor_selection_checks_bounds(tmp_path: Path) -> None:
    capture = FakeCapture()
    library = UGAFKeywords(output_dir=tmp_path, capture=capture)  # type: ignore[arg-type]
    library.use_monitor(1)
    assert capture.index == 1
    with pytest.raises(ValueError, match="invalid"):
        library.use_monitor(2)


def test_input_enable_requires_matching_foreground_title(tmp_path: Path) -> None:
    library = UGAFKeywords(
        output_dir=tmp_path,
        capture=FakeCapture(),  # type: ignore[arg-type]
        focus_checker=lambda title: title == "High School Blood",
    )
    with pytest.raises(RuntimeError, match="does not match"):
        library.enable_game_input("Riot Client")
    library.enable_game_input("High School Blood")
    library._focus_checker = lambda title: False
    with pytest.raises(RuntimeError, match="foreground no longer matches"):
        library.press_key("enter")


def test_dark_frame_fails_closed(tmp_path: Path) -> None:
    frame = np.zeros((8, 8, 4), dtype=np.uint8)
    frame[:, :, 3] = 255  # BGRA alpha must not make a black image appear visible.
    library = make_library(tmp_path, frame)
    with pytest.raises(AssertionError, match="appears black"):
        library.frame_should_not_be_black()


def test_robot_summary_parses_real_output_xml_shape(tmp_path: Path) -> None:
    from qa_framework.robot.cli import _summarize_output

    xml = tmp_path / "output.xml"
    xml.write_text(
        '<robot><suite><test name="renders"><status status="PASS" message="" /></test>'
        '<test name="subtitle"><status status="FAIL" message="not found" /></test>'
        '<status status="FAIL" /></suite></robot>',
        encoding="utf-8",
    )

    result: dict[str, Any] = _summarize_output(xml)
    assert result["suite_status"] == "FAIL"
    assert result["test_count"] == 2
    assert result["passed"] == 1
    assert result["failed"] == 1
    assert result["tests"][1]["message"] == "not found"
