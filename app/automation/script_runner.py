from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from app.input.keyboard_service import KeyboardService
from app.input.mouse_service import MouseService
from app.vision.detector import ObjectDetector


class ScriptRunner:
    """Executes automation scripts against a sandboxed context.

    Scripts receive `mouse`, `keyboard`, `vision`, `log`, and `sleep` objects.
    """

    def __init__(
        self,
        mouse: MouseService,
        keyboard: KeyboardService,
        vision: ObjectDetector,
        logger: Any | None = None,
    ) -> None:
        self._mouse = mouse
        self._keyboard = keyboard
        self._vision = vision
        self._logger = logger

    def run(self, code: str, filename: str = "<script>") -> dict[str, Any]:
        """Execute script source and return the populated namespace."""
        namespace = self._namespace()

        exec(compile(code, filename, "exec"), namespace)

        return namespace

    def run_file(self, path: Path) -> dict[str, Any]:
        """Execute a Python script file and return the populated namespace."""
        code = path.read_text(encoding="utf-8")

        return self.run(code, filename=str(path))

    def _namespace(self) -> dict[str, Any]:
        return {
            "mouse": self._mouse,
            "keyboard": self._keyboard,
            "vision": self._vision,
            "sleep": time.sleep,
            "log": self._logger,
        }
