from __future__ import annotations

from pathlib import Path
from typing import Callable

import numpy as np

from app.input.keyboard_service import KeyboardService
from app.input.mouse_service import MouseService
from app.qa.report import ReportGenerator
from app.qa.test_case import TestCase, TestResult, TestRunner
from app.vision.color_detector import ColorDetector
from app.vision.detector import ObjectDetector
from app.vision.template_match import TemplateMatcher


class QAController:
    """Orchestrates QA test runs and reporting."""

    def __init__(
        self,
        vision: ObjectDetector | None = None,
        mouse: MouseService | None = None,
        keyboard: KeyboardService | None = None,
    ) -> None:
        self._vision = vision if vision is not None else ObjectDetector()
        self._mouse = mouse if mouse is not None else MouseService()
        self._keyboard = keyboard if keyboard is not None else KeyboardService()
        self._runner = TestRunner()
        self._reports = ReportGenerator()

    def run_demo(self) -> list[TestResult]:
        """Run a built-in smoke suite exercising the vision pipeline."""
        return self._runner.run(self._build_demo_cases())

    def generate_report(self, results: list[TestResult], output_dir: Path) -> Path:
        """Write an HTML report for the given results."""
        return self._reports.generate(results, output_dir)

    def _build_demo_cases(self) -> list[TestCase]:
        checker = np.zeros((20, 20, 3), dtype=np.uint8)
        checker[::2] = 200
        checker[:, 1::2] = 200

        frame = np.zeros((60, 80, 3), dtype=np.uint8)
        frame[15:35, 20:40] = checker

        matcher = TemplateMatcher()
        color_detector = ColorDetector()

        return [
            TestCase(
                name="vision: template match",
                steps=[
                    (
                        "locates checker template",
                        _assert_true(
                            lambda: matcher.match(frame, checker, threshold=0.9) is not None
                        ),
                    ),
                ],
            ),
            TestCase(
                name="vision: color detection",
                steps=[
                    (
                        "finds matching color region",
                        _assert_true(
                            lambda: color_detector.detect(frame, (200, 200, 200)) is not None
                        ),
                    ),
                    (
                        "returns none for absent color",
                        _assert_true(lambda: color_detector.detect(frame, (250, 0, 250)) is None),
                    ),
                ],
            ),
        ]


def _assert_true(check: Callable[[], bool]) -> Callable[[], None]:
    """Build a QA step that asserts a boolean check passes."""

    def run() -> None:
        if not check():
            raise AssertionError("assertion failed")

    return run
