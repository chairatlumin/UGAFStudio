from __future__ import annotations

from datetime import datetime
from pathlib import Path


def timestamp() -> str:
    """Return a filesystem-safe UTC timestamp string."""
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def ensure_directory(path: Path) -> Path:
    """Create the directory if missing and return it."""
    path.mkdir(parents=True, exist_ok=True)
    return path


def unique_path(directory: Path, prefix: str, suffix: str) -> Path:
    """Return a unique path under directory using a timestamped name."""
    ensure_directory(directory)

    base = f"{prefix}_{timestamp()}"

    path = directory / f"{base}.{suffix}"

    counter = 1

    while path.exists():
        path = directory / f"{base}_{counter}.{suffix}"
        counter += 1

    return path
