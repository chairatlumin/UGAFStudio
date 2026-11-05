---
description: Run the non-blocking Hermes/Codex handoff review automatically.
---

Run an automatic implementation review for the current task.

Read `.ai/AUTO_REVIEW_POLICY.md`, `.ai/PLAN.md`, `.ai/ACCEPTANCE.md`, and `.ai/RESULT.md`. Inspect the current git diff and validate the recorded evidence. Run only safe, in-scope checks needed for the acceptance criteria.

Decision rules:

- Routine issues and non-critical follow-ups are recorded and auto-approved.
- Missing live-game evidence is `UNVERIFIED`, not a blocker, unless the active acceptance criteria explicitly require it.
- Stop only for the critical gates listed in `.ai/AUTO_REVIEW_POLICY.md`.

Update `.ai/REVIEW.md` with the decision, evidence, findings, and next task. If implementation work remains and no critical gate exists, update `.ai/PLAN.md` with the next actionable task so Hermes can continue without waiting for manual approval.

Never claim a check passed without running it or citing exact evidence. Do not commit, push, merge, delete user data, or perform external writes.
