# Robot Framework integration

UGAF exposes its screen capture, OCR, color detection, and input controls as
Robot Framework keywords. It is useful for readable, repeatable test cases;
Robot Framework complements the existing pytest and FMV runners.

## Install

From the repository root, install the optional extra in the UGAF environment:

```powershell
python -m pip install -e ".[robot]"
```

The extra pins Robot Framework to its supported 7.x line and installs the
existing PyAutoGUI-backed input adapter and Pillow image-header validation.
Robot Framework 7.3 added official Python 3.14 compatibility; UGAF Studio
itself requires Python 3.14.

## Run a suite

```powershell
ugaf-robot qa_framework/robot/examples/screen_smoke.robot --output-dir reports/robot
```

Use tags and per-run variables to select a genre/game-specific subset without
changing the suite source:

```powershell
ugaf-robot qa_framework/robot/examples --include smoke --exclude slow `
  --variable PROFILE:highschoolblood-demo --output-dir reports/robot
```

The wrapper also supports `--dry-run` for suite syntax and import checks.

## Run through Hermes or OpenCode

The local UGAF MCP server exposes `run_robot_suite`. Hermes and OpenCode can
call it through the configured MCP connection, selecting a suite or folder,
include/exclude tags, Robot variables, an output folder, an optional dry run,
and a UGAF game `profile`. The tool launches Robot in a separate worker,
applies a bounded timeout, and returns the run manifest and report paths. To
sync testcase results, tag each Robot test with the canonical case ID:

```robot
*** Test Cases ***
Main menu subtitle is visible
    [Tags]    subtitle    case:HBS-0001
    Text Should Be Visible    New Game
```

With a profile selected, Robot results are stored in that profile's SQLite
database and testcase reports can be fetched with `get_testcase_report` or
exported as DOCX/HTML/CSV. `qa_status` becomes `PASS` only when every selected
Robot test maps to a known testcase and passes; unmapped tests keep it
`UNASSERTED`, and a failed Robot test marks the run `FAIL`. Dry runs do not
write QA results. Screenshot keywords save under the timestamped run's
`screenshots` folder. The MCP tool does not override Robot's explicit input
gate or foreground-window checks.

To run from the packaged Windows Workbench and get a concise status in the
terminal, use:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/run_robot_suite.ps1 `
  -Suite qa_framework/robot/examples/screen_smoke.robot `
  -Include smoke -DryRun
```

This invokes the bundled Robot worker, then prints the newest run manifest and
HTML report path. In the frozen Workbench, worker diagnostics are written under
`dist/UGAF-QA/logs`.

If the project is not installed as an editable package, run the module instead:

```powershell
python -m qa_framework.robot.cli qa_framework/robot/examples/screen_smoke.robot
```

Each run creates `output.xml`, Robot's `log.html` and `report.html`, plus
`run_manifest.json` under a timestamped output folder. The manifest includes a
SHA-256 of the suite file and Robot test counts. It also lists each generated
XML, HTML, screenshot, and other evidence file with a path relative to the run
folder, byte size, and SHA-256 so report artifacts can be checked after export
or transfer. `qa_status` remains
`UNASSERTED` until UGAF can link Robot requirements and evidence to its canonical
testcase database; Robot's own suite status is kept separately.

## Keywords

| Keyword | Purpose |
| --- | --- |
| `Use Monitor` | Select display index; 0 means virtual desktop, 1 primary |
| `Capture Screen` | Capture the selected display for later assertions |
| `Save Screenshot` | Capture and save a PNG under Robot's screenshot output folder |
| `Frame Should Not Be Black` | Check visible-pixel ratio against a threshold |
| `Text Should Be Visible` | Assert OCR text in the current screen |
| `Wait For Text` | Poll OCR until text appears or timeout, saving evidence on success |
| `Color Should Be Present` | Assert a BGR color is visible within a tolerance |
| `Enable Game Input` | Unlock input only when the named game window is foreground |
| `Click At`, `Press Key`, `Type Text` | Send input after it has been explicitly enabled |
| `Set Decision API Endpoint` | Configure a loopback-only local decision endpoint |
| `Decision API Should Be Ready` | Check API/VLM readiness and optionally require an exact model ID |
| `Ask Next Action` | Submit the current frame to the decision API and return one validated suggestion |
| `Apply Decision` | Revalidate and execute only the latest unmodified suggestion after input is enabled |

Input stays disabled until a suite executes `Enable Game Input` with the expected
window title, for example `Enable Game Input    High School Blood [ Demo ]`.
UGAF checks that title again before every input and stops if focus changes.
Coordinates for `Click At` are absolute desktop coordinates. The sample suite
is read-only by default.

## Example interactive flow

```robot
*** Settings ***
Library           qa_framework.robot.library.UGAFKeywords
Test Setup        Enable Game Input    High School Blood [ Demo ]

*** Test Cases ***
Open Main Menu
    Press Key    enter
    Wait For Text    Start    timeout=20    interval=0.5
    Save Screenshot    main-menu
```

Use Robot tags such as `smoke`, `subtitle`, `minigame`, and `story` to select
test groups with Robot's `--include` / `--exclude` options in its native CLI or
the `ugaf-robot` wrapper. The wrapper records tags and variables in each run
manifest. Robot result import into the profile testcase/campaign database is
follow-up work.

## Local Decision API

Start the API in another terminal while the local VLM service (for example LM
Studio) is available:

```powershell
ugaf-decision-api --base-url http://127.0.0.1:1234/v1 --model qwen/qwen2.5-vl-7b
```

With the packaged Workbench, start it as a local worker using
`UGAF-QA.exe --qa-worker qa_framework.robot.decision_api`. Use the source
environment or `ugaf-decision-api` entry point when console output is needed.

It binds to `127.0.0.1` only and provides `GET /healthz` and
`POST /v1/decision`. The POST body contains `image_base64`, optional `context`,
and an `allowed_actions` list. Supported actions are `noop`, `click`, and
`key_press`; `noop` is always allowed as a safe fallback. The response contains
`decision_id`, action/params, model, fallback flag, and SHA-256 of the exact
decoded frame. `/healthz` probes the configured VLM `/models` endpoint and
returns HTTP 503 while it is unavailable. The decision server never sends input
itself.

Robot can request and then explicitly apply one decision:

```robot
*** Settings ***
Library    qa_framework.robot.library.UGAFKeywords

*** Test Cases ***
Choose A Visible Story Option
    ${decision}=    Ask Next Action    Game: HighSchoolBloodDemo; testcase: HBS-0002
    Should Be Equal    ${decision}[action]    click
    Enable Game Input    High School Blood [ Demo ]
    Apply Decision    ${decision}
```

The Robot library allows **3 seconds** between receiving a decision and applying
it. After that, it discards the recommendation and requires a fresh screenshot
and decision. This limits delayed clicks on a screen that may have advanced;
the explicit foreground-window check and action/frame-bound validation still run
at apply time.

For optional bearer-token protection, set `UGAF_DECISION_API_TOKEN` before
starting the API and pass the same token to `Set Decision API Endpoint`. VLM
configuration can be supplied through `VLM_BASE_URL`, `VLM_MODEL`, and
`VLM_API_KEY`. The endpoint is deliberately constrained to loopback by the
Robot client so screenshots are not accidentally sent to a remote service.

### Decision API preflight suite

`qa_framework/robot/examples/decision_api_preflight.robot` verifies the local
API/model health and sends one captured frame with the allowlist restricted to
`noop`. It cannot click or press keys, and it does not enable game input. Run it
before an interactive campaign to distinguish model/API readiness from game
window and gameplay failures:

```powershell
python -m qa_framework.robot.cli qa_framework/robot/examples/decision_api_preflight.robot `
  --include preflight --profile highschoolblood-demo --game-type fmv
```

The model name is configurable through the suite's `${EXPECTED_MODEL}` variable.
The generated Robot results show suite execution status; the UGAF manifest
continues to mark QA as `UNASSERTED` unless testcase requirements and in-game
evidence are linked.
