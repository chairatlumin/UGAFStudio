from __future__ import annotations

from pathlib import Path
from typing import Any

from loguru import logger

LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)

logger.remove()

logger.add(
    LOG_DIR / "ugaf.log",
    rotation="10 MB",
    retention=10,
    level="INFO",
    encoding="utf-8",
)

logger.add(
    sink=lambda message: print(message, end=""),
    level="INFO",
)


def get_logger() -> Any:
    """Return shared logger."""

    return logger
