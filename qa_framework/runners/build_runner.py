from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass
class ProcessResult:
    started: bool
    exit_code: int | None
    pid: int | None
    error: str | None


def launch_build(
    executable: Path,
    working_directory: Path | None = None,
) -> tuple[subprocess.Popen[str] | None, ProcessResult]:

    cwd = working_directory or executable.parent

    try:
        process = subprocess.Popen(
            [str(executable)],
            cwd=str(cwd),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
        )

    except OSError as exc:
        return (
            None,
            ProcessResult(
                started=False,
                exit_code=None,
                pid=None,
                error=str(exc),
            ),
        )

    return (
        process,
        ProcessResult(
            started=True,
            exit_code=None,
            pid=process.pid,
            error=None,
        ),
    )
