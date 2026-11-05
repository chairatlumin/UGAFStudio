# HighSchool Blood QA

`highschool_blood_cases.json` is a read-only snapshot of the scene checklist
and tester feedback supplied in the Google Sheets workbook. It preserves each
scene row and its Audio, Subtitle, Choice, Overall, Final Result, and Remarks
values. It does not update the source workbook.

The snapshot contains 409 scene rows and 408 distinct scene IDs. Row-level
final statuses are 220 Pass, 39 Fail, and 150 Pending. The workbook's summary
cells report 161 total, 161 Pass, 32 Fail, and 25 Pending; those figures do not
reconcile with the detailed rows. Use the row-level values as the source for
case review and confirm the summary with the QA owner before using it for a
release gate.

## First automated check

The current gameplay runner supports launch, screenshot capture, and visual
assertions. The included suite detects a black or near-black captured frame:

```powershell
python -m qa_framework.gameplay_cli `
  --app-id 4511150 `
  --suite qa_framework/examples/game_4511150_highschoolblood_auto.json `
  --steam-root D:\SteamLibrary `
  --output-dir reports/highschool_blood
```

Alternatively, pass `--executable` with the packaged `HighSchoolBlood.exe`
and omit `--app-id` and `--steam-root`. The runner will close the process it
launches after capturing the frame. It does not modify the Google Sheet.

## Current coverage and required inputs

The black-frame assertion automates one issue recorded repeatedly in scene
feedback. It is a smoke check, not a full scene regression run. The checklist
also reports subtitle omissions, subtitle/choice overflow, stalled or looping
video, wrong branch transitions, missing audio, audio dropouts, and high-pitched
audio. Those need per-scene expected subtitle/choice text, stable branch setup
or save checkpoints, and audio loopback capture. The workbook has statuses and
remarks but no subtitle transcript, screen regions, timing tolerances, or
repeatable save-state setup, so those checks are retained in the data rather
than guessed into brittle automated assertions.

The game executable was not present in the inspected Steam install folder when
this suite was prepared. A live run needs an installed build containing
`HighSchoolBlood.exe`; audio and branch behavior have not been live-verified.
