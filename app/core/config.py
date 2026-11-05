from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

from app.core.paths import writable_path

class Config:
    """Application configuration."""

    def __init__(self) -> None:
        self.path = writable_path("config", "config.toml")
        self.data: dict[str, Any] = {}

    def load(self) -> None:
        if not self.path.exists():
            self.data = {}
            return

        with self.path.open("rb") as file:
            self.data = tomllib.load(file)

    def get(self, key: str, default: Any = None) -> Any:
        """Return a configuration value."""
        return self.data.get(key, default)
