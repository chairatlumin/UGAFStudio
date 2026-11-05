---
description: Run and record the project's QA quality gates.
---

Run the smallest complete quality-gate set for the active task from `.ai/ACCEPTANCE.md`.

Prefer the project's configured environment. Run, when applicable:

- compile/import validation
- pytest
- Ruff check and format check
- mypy
- pre-commit

Record the exact command, exit status, and concise output in `.ai/RESULT.md`. Separate passed, failed, and unverified checks. Do not fabricate results and do not treat missing optional dependencies as a pass. If a failure is non-critical, record it as a follow-up and continue the handoff; stop only when it matches a critical gate in `.ai/AUTO_REVIEW_POLICY.md`.

Do not launch real Steam games unless the active task explicitly requests a supervised live run. Never leave started processes running.
