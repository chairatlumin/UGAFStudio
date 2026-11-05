# UGAF Studio

Robot Framework suites and the local VLM decision endpoint are documented in
[`docs/robot-framework.md`](docs/robot-framework.md). Install the optional
support with `python -m pip install -e ".[robot]"`.

Universal Game QA Framework

## Features

- Desktop Capture
- Game Inspection
- Pixel Inspector
- OCR
- Template Matching
- Automation
- Reporting
- Local QA Command Center with human-reviewed action cards, safe preflight,
  and supervised FMV demo runs
- Robot Framework keywords for screen capture, OCR, color checks, and guarded
  game input
- Loopback VLM Decision API for bounded action suggestions with evidence hashes

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

## License

MIT License. See [LICENSE](LICENSE).
