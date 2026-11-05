---
description: Review an implementation for architecture, quality, and quality gates.
---

Review the current implementation and the latest Hermes handoff.

Read these files first when they exist:

- `.ai/AUTO_REVIEW_POLICY.md`
- `.ai/ACCEPTANCE.md`
- `.ai/RESULT.md`
- `.ai/PLAN.md`
- `AGENTS.md`

Apply the automatic review policy:

- Do not ask for approval for routine findings, formatting issues, ordinary test failures, or non-critical follow-ups.
- If acceptance criteria pass and no critical gate is triggered, record `AUTO-APPROVED WITH FOLLOW-UPS` in `.ai/REVIEW.md` and continue.
- Stop and ask the user only for credentials/private data exposure, destructive or irreversible actions, security boundary bypass, unreliable process cleanup, safety/data-integrity failure, or material scope expansion.
- Mark live-game or real-environment evidence as `UNVERIFIED` when it was not run; do not invent results.

Review this implementation:

- Architecture
- SOLID
- Type hints
- Naming
- Performance
- Memory usage
- Thread safety
- Test coverage
- Ruff
- Ruff Format
- mypy

Also check the git diff and exact commands/results recorded in `.ai/RESULT.md`.

Write the review to `.ai/REVIEW.md` with:

1. Status and critical-gate result.
2. Findings grouped by critical, follow-up, and unverified.
3. Acceptance summary with evidence.
4. The next concrete task for Hermes, if any.

Do not commit, push, merge, or modify unrelated files.
