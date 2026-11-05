from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, List


@dataclass
class ShutdownConfig:
    timeout_seconds: float = 30.0
    force_exit_on_timeout: bool = False


class GracefulShutdown:
    def __init__(self, config: ShutdownConfig | None = None) -> None:
        self._config: ShutdownConfig = config or ShutdownConfig()
        self._cleanup_callbacks: List[Callable[[], None]] = []
        self._shutdown: bool = False

    def register_cleanup(self, cleanup_func: Callable[[], None]) -> None:
        self._cleanup_callbacks.append(cleanup_func)

    def shutdown(self) -> None:
        if self._shutdown:
            return

        self._shutdown = True
        for cleanup_func in self._cleanup_callbacks:
            try:
                cleanup_func()
            except Exception:
                pass

        self._cleanup_callbacks.clear()