from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def writable_base() -> Path:
    """Return the stable writable root for source and frozen app runs."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return PROJECT_ROOT


def writable_path(*parts: str) -> Path:
    return writable_base().joinpath(*parts)
