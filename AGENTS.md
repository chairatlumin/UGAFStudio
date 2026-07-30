# UGAF Studio - AI Agent Guide

## Mission

Build a production-quality Game QA Automation Framework.

## Tech Stack

- Python 3.14
- PySide6
- OpenCV
- NumPy
- MSS
- Loguru

## Architecture Rules

- MainWindow contains UI only.
- Controllers orchestrate Services.
- Services contain business logic.
- Widgets never contain business logic.

## Quality Gates

Every change must pass:

- Ruff
- Ruff Format
- mypy
- pytest
- pre-commit

## Current Phase

Desktop Inspector

## Current Features

- Live Preview
- Capture Controller
- FPS Counter
- Mouse Position
- Resolution

## Next Sprint

Pixel Inspector
