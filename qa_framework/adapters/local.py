"""Local executable target adapter for engine-agnostic gameplay QA."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class LocalGame:
    """A game launched from an executable, independent of distribution platform."""

    app_id: str
    name: str
    install_path: Path


def local_game_from_executable(executable: str | Path, name: str | None = None) -> LocalGame:
    """Build a target from any engine's packaged executable."""
    path = Path(executable).resolve()
    if not path.is_file():
        raise FileNotFoundError(f"Game executable not found: {path}")
    return LocalGame(
        app_id=f"local:{path.stem}",
        name=name or path.stem,
        install_path=path.parent,
    )
