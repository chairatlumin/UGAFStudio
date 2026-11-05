#!/usr/bin/env python3
"""Per-file `ruff format --check` across app/, qa_framework/, tests/, scripts/.

Bulk `ruff format .` panics on ruff 0.16.1 for large files, blocking the whole
run. Checking one file per invocation isolates any panic to a single line.
Check-only: modifies nothing. Exits nonzero if any file fails.
Usage: C:\\Python314\\python.exe scripts/format_all.py
"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIRS = ["app", "qa_framework", "tests", "scripts"]
SKIP = {".venv", "__pycache__", ".pytest-tmp", ".pytest_cache",
        ".ruff_cache", ".mypy_cache", ".git", ".idea"}


def main() -> int:
    files = sorted(
        p for d in DIRS for p in (ROOT / d).rglob("*.py") if not SKIP & set(p.parts)
    ) + sorted(ROOT.glob("*.py"))
    failed, passed = [], 0
    for f in files:  # ponytail: one ruff per file; a panic fails one line, not the run
        r = subprocess.run(
            [sys.executable, "-m", "ruff", "format", "--check", str(f)],
            capture_output=True, text=True, timeout=60,
        )
        print(f"  [{'PASS' if r.returncode == 0 else 'FAIL'}] {f.relative_to(ROOT)}")
        passed += r.returncode == 0
        if r.returncode != 0:
            failed.append(str(f.relative_to(ROOT)))
    print(f"\n{passed} passed, {len(failed)} failed out of {len(files)} files")
    if failed:
        print("Failed files:\n  - " + "\n  - ".join(sorted(failed)))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
