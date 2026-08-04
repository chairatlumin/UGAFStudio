from __future__ import annotations

from datetime import datetime


def now_ms() -> float:
    """Return current epoch time in milliseconds."""
    return datetime.now().timestamp() * 1000.0
