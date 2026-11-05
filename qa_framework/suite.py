from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional

import cv2
import numpy as np

from app.qa.test_case import StepResult, TestCase, TestResult, TestRunner
from app.vision.color_detector import ColorDetector
from qa_framework.core.engine import is_supported_version
from qa_framework.metrics import RecoveryTracker
from qa_framework.verification import Checkpoint, QARun


@dataclass(frozen=True)
class Suite:
    name: str
    cases: list[TestCase]


def load_suite(path: str | Path) -> Suite:
    """Load a declarative QA suite from a JSON file."""
    suite_path = Path(path).resolve()
    data = json.loads(suite_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Suite root must be a JSON object.")

    name = data.get("name", suite_path.stem)
    raw_cases = data.get("tests")
    if not isinstance(name, str) or not name.strip():
        raise ValueError("Suite name must be a non-empty string.")
    if not isinstance(raw_cases, list) or not raw_cases:
        raise ValueError("Suite must contain a non-empty 'tests' array.")

    cases = [_load_case(case, suite_path.parent, index) for index, case in enumerate(raw_cases)]
    return Suite(name=name, cases=cases)


def run_suite(suite: Suite, enable_verification: bool = False) -> list[TestResult]:
    """Run all test cases in the suite.

    Args:
        suite: The QA suite to run.
        enable_verification: If True, wrap each test in a QARun with checkpoints
            and track recovery incidents.
    """
    if not enable_verification:
        return TestRunner().run(suite.cases)

    # Verification-enabled path: wrap each test case in a QARun
    global last_recovery_tracker
    last_recovery_tracker = RecoveryTracker()
    results: list[TestResult] = []

    for case in suite.cases:
        qar = QARun(
            name=case.name,
            checkpoints=[
                Checkpoint(
                    name=step_name,
                    condition=_make_safe_step(action),
                    timeout=30.0,
                )
                for step_name, action in case.steps
            ],
        )

        passed = qar.run()
        if not passed:
            # Attempt recovery: retry once
            last_recovery_tracker.record_incident("retry", False)
            passed = qar.run()  # second attempt
            last_recovery_tracker.record_incident("retry", passed)

        # Convert QARun result to TestResult
        step_results = [
            StepResult(
                name=cp.name,
                passed=cp.result,
                message="passed" if cp.result else "failed",
                duration_ms=cp.elapsed * 1000.0,
            )
            for cp in qar.checkpoints
        ]
        results.append(TestResult(
            name=case.name,
            passed=passed,
            duration_ms=qar.elapsed() * 1000.0,
            steps=step_results,
        ))

    return results


def _make_safe_step(action: Callable[[], None]) -> Callable[[], bool]:
    """Wrap a step action as a boolean condition for Checkpoint."""
    def condition() -> bool:
        try:
            action()
            return True
        except Exception:
            return False
    return condition


# Module-level access to the last run's recovery tracker
last_recovery_tracker: RecoveryTracker | None = None


def _load_case(raw_case: Any, base_dir: Path, index: int) -> TestCase:
    if not isinstance(raw_case, dict):
        raise ValueError(f"Test at index {index} must be an object.")
    name = raw_case.get("name")
    raw_steps = raw_case.get("steps")
    if not isinstance(name, str) or not name.strip():
        raise ValueError(f"Test at index {index} needs a non-empty name.")
    if not isinstance(raw_steps, list) or not raw_steps:
        raise ValueError(f"Test '{name}' must contain a non-empty 'steps' array.")

    steps: list[tuple[str, Callable[[], None]]] = []
    for step_index, raw_step in enumerate(raw_steps):
        if not isinstance(raw_step, dict):
            raise ValueError(f"Step {step_index} in '{name}' must be an object.")
        step_name = raw_step.get("name", f"step {step_index + 1}")
        check = raw_step.get("check")
        if not isinstance(step_name, str) or not isinstance(check, str):
            raise ValueError(f"Step {step_index} in '{name}' needs name and check.")
        steps.append((step_name, _build_check(check, raw_step, base_dir)))
    return TestCase(name=name, steps=steps)


def _build_check(check: str, step: dict[str, Any], base_dir: Path) -> Callable[[], None]:
    if check == "file_exists":
        path = _required_path(step, base_dir)
        return _assert(path.is_file, f"File does not exist: {path}")
    if check == "directory_exists":
        path = _required_path(step, base_dir)
        return _assert(path.is_dir, f"Directory does not exist: {path}")
    if check == "executable_count":
        path = _required_path(step, base_dir)
        expected = _required_int(step, "expected")
        return _assert(
            lambda: len(list(path.glob("*.exe"))) == expected,
            f"Expected {expected} executable(s) in {path}",
        )
    if check == "engine_version_supported":
        version = step.get("version")
        if not isinstance(version, str):
            raise ValueError("engine_version_supported requires a string 'version'.")
        return _assert(
            lambda: is_supported_version(version),
            f"Unsupported Unreal Engine version: {version}",
        )
    if check == "color_detected":
        raw_color = step.get("color")
        if not _is_bgr_tuple(raw_color):
            raise ValueError("color_detected requires 'color' as [b, g, r].")
        color = tuple(raw_color)  # type: ignore[arg-type]
        tolerance = int(step.get("tolerance", 30))
        return _assert(
            lambda: _color_matches(path, color, tolerance),
            f"Color not detected: expected [{color[0]}, {color[1]}, {color[2]}]",
        )
    if check == "template_match":
        template_path = step.get("template")
        if not isinstance(template_path, str) or not template_path.strip():
            raise ValueError("template_match requires a 'template' path.")
        template = cv2.imread(template_path, cv2.IMREAD_UNCHANGED)
        if template is None:
            raise FileNotFoundError(f"Template image not found: {template_path}")
        threshold = float(step.get("threshold", 0.9))
        return _assert(
            lambda: _template_matches(path, template, threshold),
            f"Template not matched: {template_path} threshold={threshold:.2f}",
        )
    if check == "ocr_contains":
        expected_text = step.get("text")
        if not isinstance(expected_text, str) or not expected_text.strip():
            raise ValueError("ocr_contains requires 'text'.")

        raw_path = step.get("path")
        ocr_path = _required_path(step, base_dir) if isinstance(raw_path, str) else None

        def _ocr_check() -> bool:
            try:
                if ocr_path is None:
                    return False
                frame = cv2.imread(str(ocr_path), cv2.IMREAD_UNCHANGED)
                if frame is None:
                    return False
                import pytesseract

                text = pytesseract.image_to_string(frame)
                return expected_text.lower() in text.lower()
            except Exception:
                return False

        return _assert(_ocr_check, f"OCR text did not contain {expected_text!r}")
    raise ValueError(f"Unsupported QA check: {check}")


def _required_path(step: dict[str, Any], base_dir: Path) -> Path:
    value = step.get("path")
    if not isinstance(value, str) or not value.strip():
        raise ValueError("This check requires a non-empty 'path'.")
    path = Path(value)
    return (base_dir / path).resolve() if not path.is_absolute() else path.resolve()


def _required_int(step: dict[str, Any], key: str) -> int:
    value = step.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"This check requires integer '{key}'.")
    return value


def _assert(check: Callable[[], bool], message: str) -> Callable[[], None]:
    def run() -> None:
        if not check():
            raise AssertionError(message)

    return run


def _color_matches(path: Path, color: tuple[int, int, int], tolerance: int) -> bool:
    detector = ColorDetector()
    frame = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
    if frame is None:
        return False
    result = detector.detect(frame, color, tolerance=tolerance)
    return result is not None


def _template_matches(path: Path, template: np.ndarray, threshold: float) -> bool:
    from app.vision.template_match import TemplateMatcher

    matcher = TemplateMatcher()
    frame = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
    if frame is None:
        return False
    match = matcher.match(frame, template, threshold=threshold)
    return match is not None


def _ocr_check(path: Optional[Path], expected: str) -> bool:
    import pytesseract

    try:
        if path is not None:
            frame = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
        else:
            frame = np.zeros((10, 10, 3), dtype=np.uint8)
        if frame is None:
            return False
        text = pytesseract.image_to_string(frame)
        return expected.lower() in text.lower()
    except Exception:
        return False


def _is_bgr_tuple(value: Any) -> bool:
    return (
        isinstance(value, (list, tuple))
        and len(value) == 3
        and all(isinstance(channel, int) for channel in value)
    )
