# UGAF Studio Agent Handoff

This directory is the shared handoff area between the planning/review agent
(ChatGPT Codex) and the implementation agent (Hermes).

## Workflow

1. Codex updates `PLAN.md`, `ACCEPTANCE.md`, and one task under `TASKS/`.
2. Hermes reads the active task, implements it, and records work in `RESULT.md`.
3. Hermes runs the checks listed in `ACCEPTANCE.md` and records exact commands and results.
4. Codex reviews the git diff and `RESULT.md`, then records the decision in `REVIEW.md`.
5. Only after review should the implementation branch be merged.

## Rules

- Work in `C:\Users\Admin\UGAFStudio`.
- Preserve unrelated user changes.
- Do not commit secrets, auth tokens, or Steam credentials.
- Do not claim a check passed without recording its command and output.
- Keep one active task at a time unless tasks are explicitly independent.

## Branch convention

Use `hermes/<task-slug>` for implementation branches and `codex/<task-slug>`
for planning or review branches.
