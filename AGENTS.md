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

QA Framework (all roadmap phases implemented)

## Current Features

- Live Preview
- Multi-monitor capture (virtual desktop)
- Pixel Inspector (RGB + HEX)
- Screenshot
- Region Capture
- Vision: Template Matching, Color Detection, OCR
- Automation: Mouse, Keyboard, Hotkeys, Gamepad, Macro, Script Runner
- QA: Test Runner, HTML Report, Dashboard
- GUI: Capture + QA menus, Dashboard tab, Logger

## Next Sprint

- OCR tuning
- Macro UI recording
- Scripted QA test cases from disk
