# Acceptance Criteria

## Required

- `python -m compileall -q app qa_framework tests` exits with code 0.
- Existing Steam discovery still lists the three selected games.
- A selected game can be launched with a configurable timeout.
- A failed startup produces a failed test result and an HTML report.
- A successful run always cleans up the process it started.
- At least one visual assertion can be configured from JSON.
- Existing tests remain compatible.

## Report requirements

Every run must include:

- game name and App ID;
- install path;
- test and step status;
- failure message;
- duration;
- report path;
- process cleanup status.

## Not accepted

- Hard-coded absolute paths to one developer's machine;
- silently swallowing launch failures;
- leaving a game process running after a failed test;
- treating file existence as gameplay validation.
