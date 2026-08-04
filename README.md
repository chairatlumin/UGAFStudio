# UGAF Studio

Universal Game QA Framework

## Features

- Desktop Capture
- Game Inspection
- Pixel Inspector
- OCR
- Template Matching
- Automation
- Reporting

## Requirements

- Python 3.14
- Windows 11

## Installation

pip install -r requirements.txt

## Run

python main.py

## Quality

pre-commit run --all-files

pytest

## Project Structure

```text
app/       Application package (capture, vision, automation, input, gui,
           controllers, core, qa, utils, database)
config/    Application configuration
models/    Shared data models
services/  Service layer
tests/     Automated tests
docs/      Developer notes and design records
scripts/   Developer tooling
main.py    Application entry point
launcher.py
```
