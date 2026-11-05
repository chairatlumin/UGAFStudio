"""Shared utility helpers for qa_framework."""

from __future__ import annotations

from pathlib import Path


def ensure_dir(path: Path) -> None:
    """Ensure a directory exists, creating parents if necessary."""
    path.mkdir(parents=True, exist_ok=True)
