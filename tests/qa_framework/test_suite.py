import json
from pathlib import Path

import pytest

from qa_framework.suite import load_suite, run_suite


def test_load_and_run_declarative_suite(tmp_path: Path) -> None:
    (tmp_path / "build").mkdir()
    (tmp_path / "build" / "Game.exe").write_bytes(b"")
    suite_file = tmp_path / "suite.json"
    suite_file.write_text(
        json.dumps(
            {
                "name": "Smoke",
                "tests": [
                    {
                        "name": "Build",
                        "steps": [
                            {"name": "folder", "check": "directory_exists", "path": "build"},
                            {
                                "name": "exe",
                                "check": "executable_count",
                                "path": "build",
                                "expected": 1,
                            },
                        ],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    results = run_suite(load_suite(suite_file))

    assert len(results) == 1
    assert results[0].passed
    assert len(results[0].steps) == 2


def test_failed_check_is_reported_as_test_failure(tmp_path: Path) -> None:
    suite_file = tmp_path / "suite.json"
    suite_file.write_text(
        json.dumps(
            {
                "tests": [
                    {
                        "name": "Missing build",
                        "steps": [
                            {"name": "folder", "check": "directory_exists", "path": "missing"}
                        ],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    result = run_suite(load_suite(suite_file))[0]

    assert not result.passed
    assert "does not exist" in result.steps[0].message


def test_unknown_check_is_rejected(tmp_path: Path) -> None:
    suite_file = tmp_path / "suite.json"
    suite_file.write_text(
        json.dumps({"tests": [{"name": "Bad", "steps": [{"name": "x", "check": "unknown"}]}]}),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Unsupported QA check"):
        load_suite(suite_file)


def test_ocr_unavailable_when_tesseract_missing(tmp_path: Path) -> None:
    """Verify that ocr_contains gracefully reports unavailable instead of crashing.

    This test documents the expected behaviour when Tesseract is not installed:
    the assertion passes=False with a clear message rather than raising an exception.
    """
    suite_file = tmp_path / "suite.json"
    suite_file.write_text(
        json.dumps(
            {
                "name": "OCR Test",
                "tests": [
                    {
                        "name": "ocr contains text",
                        "steps": [
                            {
                                "name": "check for Play button",
                                "check": "ocr_contains",
                                "text": "Play",
                            }
                        ],
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    results = run_suite(load_suite(suite_file))
    assert len(results) == 1
    assert not results[0].passed
    # When Tesseract binary is absent, pytesseract reports its error in its
    # own message; we just verify the assertion fails gracefully rather than
    # raising an exception.
    assert "OCR" in results[0].steps[0].message
    assert "text" in results[0].steps[0].message.lower()


def test_directory_exists_relative_to_suite(tmp_path: Path) -> None:
    (tmp_path / "mydir").mkdir()
    suite_file = tmp_path / "suite.json"
    suite_file.write_text(
        json.dumps(
            {
                "name": "Test",
                "tests": [
                    {
                        "name": "dir relative to suite",
                        "steps": [
                            {
                                "name": "mydir exists",
                                "check": "directory_exists",
                                "path": "mydir",
                            }
                        ],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    results = run_suite(load_suite(suite_file))
    assert len(results) == 1
    assert results[0].passed


def test_executable_count_with_zero(tmp_path: Path) -> None:
    # Create a subdirectory with no .exe files
    empty_dir = tmp_path / "emptydir"
    empty_dir.mkdir()
    suite_file = tmp_path / "suite.json"
    suite_file.write_text(
        json.dumps(
            {
                "name": "Test",
                "tests": [
                    {
                        "name": "exe count zero",
                        "steps": [
                            {
                                "name": "no exe in subdir",
                                "check": "executable_count",
                                "path": str(empty_dir),
                                "expected": 0,
                            }
                        ],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    results = run_suite(load_suite(suite_file))
    assert len(results) == 1
    assert results[0].passed


def test_failed_check_reports_message(tmp_path: Path) -> None:
    suite_file = tmp_path / "suite.json"
    suite_file.write_text(
        json.dumps(
            {
                "tests": [
                    {
                        "name": "Missing folder",
                        "steps": [
                            {
                                "name": "nonexistent folder",
                                "check": "directory_exists",
                                "path": "nonexistent",
                            }
                        ],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    result = run_suite(load_suite(suite_file))[0]
    assert not result.passed
    assert "does not exist" in result.steps[0].message
