---
description: Review Python changes for secure-by-default behavior.
---

Run a focused security review for the current Python changes. Read `AGENTS.md`, `.ai/AUTO_REVIEW_POLICY.md`, and `.ai/RESULT.md`, then inspect the git diff.

Check at minimum:

- secrets, tokens, private keys, personal data, and unsafe logging
- subprocess usage, executable/path resolution, shell injection, and argument handling
- unsafe deserialization, arbitrary file writes, path traversal, and uncontrolled network access
- process cleanup, sandbox boundaries, permissions, and failure handling
- Steam/game launch inputs and protection against launching unintended executables

Write findings to `security_best_practices_report.md` with an executive summary, numeric IDs, severity, impact, file/line evidence, and remediation. If no material issue is found, state that explicitly and list unverified areas.

Do not modify application code, commit, push, merge, or request approval for routine findings. Stop only when a critical gate in `.ai/AUTO_REVIEW_POLICY.md` is triggered.
