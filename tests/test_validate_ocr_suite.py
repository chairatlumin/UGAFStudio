from __future__ import annotations

import tempfile
from pathlib import Path

import cv2
import numpy as np

from scripts.validate_ocr_suite import validate_suite

_ASSETS = Path(__file__).resolve().parents[1] / "scripts"


def _draw_text_frame(text: str, size: tuple[int, int] = (640, 360)) -> np.ndarray:
    frame = np.full((size[1], size[0], 3), 255, dtype=np.uint8)
    cv2.putText(
        frame,
        text,
        (size[0] // 2 - len(text) * 18, size[1] // 2),
        cv2.FONT_HERSHEY_SIMPLEX,
        2.0,
        (0, 0, 0),
        4,
        cv2.LINE_AA,
    )
    return frame


def _write_frame(directory: Path, name: str, frame: np.ndarray) -> Path:
    path = directory / name
    cv2.imwrite(str(path), frame)
    return path


def test_validator_runs_ocr_assertion_on_generated_frame() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        evidence = Path(tmp)
        _write_frame(evidence, "ul_menu.png", _draw_text_frame("START"))

        suite: dict = {
            "app_id": 4511140,
            "name": "generated",
            "assertions": [{"name": "shows START", "check": "ocr_word_present", "text": "START"}],
        }

        results = validate_suite(suite, evidence)
        assert len(results) == 1
        assert results[0]["status"] == "PASS"
        assert results[0]["passed"] is True


def test_validator_skips_when_no_evidence() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        evidence = Path(tmp)

        suite: dict = {
            "app_id": 4511140,
            "name": "generated",
            "assertions": [{"name": "shows START", "check": "ocr_word_present", "text": "START"}],
        }

        results = validate_suite(suite, evidence)
        assert len(results) == 1
        assert results[0]["status"] == "SKIP"
        assert results[0]["evidence"] == "(none)"


def test_validator_reports_failure() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        evidence = Path(tmp)
        _write_frame(evidence, "ul_blank.png", np.full((360, 640, 3), 255, np.uint8))

        suite: dict = {
            "app_id": 4511140,
            "name": "generated",
            "assertions": [
                {"name": "shows MISSING", "check": "ocr_word_present", "text": "MISSING"}
            ],
        }

        results = validate_suite(suite, evidence)
        assert len(results) == 1
        assert results[0]["status"] == "FAIL"
        assert results[0]["passed"] is False
