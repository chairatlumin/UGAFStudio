from __future__ import annotations

import runpy
import sys
from datetime import UTC, datetime
from pathlib import Path

_ALLOWED_QA_WORKERS = {
    "scripts.fmv_harness",
    "scripts.live_gameplay_agent",
    "qa_framework.robot.cli",
    "qa_framework.robot.decision_api",
}
_QA_WORKER_LOG: object | None = None


def _normalize_worker_module(raw: str) -> str:
    module = raw.replace("/", ".").replace("\\", ".")
    if module.endswith(".py"):
        module = module[: -len(".py")]
    module = module.strip(".")
    if module in {"fmv_harness", "live_gameplay_agent"}:
        module = f"scripts.{module}"
    if module not in _ALLOWED_QA_WORKERS:
        raise SystemExit(f"Refusing to run unknown worker module {raw!r}.")
    return module


def _run_qa_worker(argv: list[str]) -> None:
    """Dispatch frozen worker children through the same executable.

    Source installs keep using ``python scripts/<name>.py``; packaged runs
    invoke ``UGAF-QA.exe --qa-worker <allowlisted-module> ...`` so no sibling
    interpreter or script files are needed beside the exe.
    """
    if not argv:
        raise SystemExit("--qa-worker requires a module name.")
    module = _normalize_worker_module(argv[0])
    _configure_frozen_worker_output()
    sys.argv = [module, *argv[1:]]
    runpy.run_module(module, run_name="__main__")


def _configure_frozen_worker_output() -> None:
    """Redirect windowed frozen worker output to a persistent log file."""
    global _QA_WORKER_LOG
    if not getattr(sys, "frozen", False) or (sys.stdout is not None and sys.stderr is not None):
        return
    root = Path(sys.executable).resolve().parent
    log_dir = root / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"qa_worker_{datetime.now(UTC):%Y%m%dT%H%M%S%fZ}.log"
    _QA_WORKER_LOG = log_path.open("a", encoding="utf-8", buffering=1)
    if sys.stdout is None:
        sys.stdout = _QA_WORKER_LOG  # type: ignore[assignment]
    if sys.stderr is None:
        sys.stderr = _QA_WORKER_LOG  # type: ignore[assignment]


def main() -> None:
    """Application entry point."""

    if len(sys.argv) > 1 and sys.argv[1] == "--qa-worker":
        _run_qa_worker(sys.argv[2:])
        return

    from PySide6.QtWidgets import QApplication

    from app.core.application import UGAFApplication

    workbench_only = "--qa-workbench" in sys.argv
    if workbench_only:
        sys.argv = [arg for arg in sys.argv if arg != "--qa-workbench"]

    app = QApplication(sys.argv)

    application = UGAFApplication(app)

    if workbench_only:
        try:
            application.window.show_workbench()
        except AttributeError:
            pass

    application.start()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
