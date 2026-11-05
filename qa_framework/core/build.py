from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class BuildInfo:
    name: str
    root: Path
    executable: Path


def find_executable(build_dir: Path) -> Path:
    executables = list(build_dir.glob("*.exe"))

    if not executables:
        raise FileNotFoundError(f"No .exe found in build directory: {build_dir}")

    if len(executables) > 1:
        names = ", ".join(exe.name for exe in executables)

        raise RuntimeError(
            f"Multiple .exe files found. Specify the game executable explicitly: {names}"
        )

    return executables[0]


def discover_build(build_dir: str | Path) -> BuildInfo:
    root = Path(build_dir).resolve()

    if not root.exists():
        raise FileNotFoundError(f"Build directory does not exist: {root}")

    if not root.is_dir():
        raise NotADirectoryError(f"Build path is not a directory: {root}")

    executable = find_executable(root)

    return BuildInfo(
        name=executable.stem,
        root=root,
        executable=executable,
    )
