import json
from pathlib import Path

import pytest

from qa_framework.core.build import discover_build, find_executable
from qa_framework.core.engine import (
    detect_engine_version,
    is_supported_version,
    normalize_engine_version,
)
from qa_framework.core.project import find_uproject, load_project


def test_discover_build_requires_exactly_one_executable(tmp_path: Path) -> None:
    executable = tmp_path / "Game.exe"
    executable.write_bytes(b"")
    build = discover_build(tmp_path)
    assert build.name == "Game"
    assert build.root == tmp_path.resolve()
    assert build.executable == executable


def test_find_executable_rejects_multiple_executables(tmp_path: Path) -> None:
    (tmp_path / "Client.exe").write_bytes(b"")
    (tmp_path / "Editor.exe").write_bytes(b"")
    with pytest.raises(RuntimeError, match=r"Multiple \.exe files"):
        find_executable(tmp_path)


def test_load_project_reads_engine_association(tmp_path: Path) -> None:
    project_file = tmp_path / "Demo.uproject"
    project_file.write_text(json.dumps({"EngineAssociation": "5.8"}), encoding="utf-8")
    project = load_project(project_file)
    assert project.name == "Demo"
    assert project.path == project_file.resolve()
    assert project.engine_association == "5.8"


def test_find_uproject_rejects_missing_and_ambiguous_projects(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        find_uproject(tmp_path)
    (tmp_path / "A.uproject").write_text("{}", encoding="utf-8")
    (tmp_path / "B.uproject").write_text("{}", encoding="utf-8")
    with pytest.raises(RuntimeError, match=r"Multiple \.uproject files"):
        find_uproject(tmp_path)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("5.7", "5.7"), ("UE_5.8-preview", "5.8"), ("4.27", None), (None, None)],
)
def test_normalize_engine_version(raw: str | None, expected: str | None) -> None:
    assert normalize_engine_version(raw) == expected
    assert detect_engine_version(raw) == expected


def test_supported_engine_versions_are_explicit() -> None:
    assert is_supported_version("5.7")
    assert is_supported_version("5.8")
    assert not is_supported_version("5.9")
    assert not is_supported_version(None)
