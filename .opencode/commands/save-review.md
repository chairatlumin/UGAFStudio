---
description: Save a completed PR review report from /review-pr into reports/pr-<PR_NUMBER>-review.md. Usage: /save-review owner/repo PR_NUMBER
agent: build
---

Save the completed PR review report for the target pull request into `reports/pr-<PR_NUMBER>-review.md`.

Target pull request: `$ARGUMENTS`

Parse `owner/repo` and the PR number from `$ARGUMENTS`. If the identifier is missing or ambiguous (no `owner/repo` and PR number provided), stop and ask the user for `owner/repo` and the PR number before doing anything else.

## Steps

1. Locate the completed review report produced by `/review-pr` for the target pull request in the current session.
2. If the review report is not available (it was not produced, or it does not correspond to the target pull request), stop and report that the review result cannot be saved. Do not fabricate one.
3. Create the `reports` directory if it does not exist.
4. Save the full review report to `reports/pr-<PR_NUMBER>-review.md`, preserving the content exactly as produced. Do not invent, summarize, reword, or alter any findings, severities, or recommendations.
5. Confirm the saved path and report the result.

## Constraints

- Preserve the review content exactly; do not invent, summarize, or alter findings.
- This command exists only to persist the review artifact.
- Do not modify application source code.
- Do not modify tests.
- Do not commit, do not push, do not merge.
- Do not approve or submit a GitHub review.
- Do not modify any file other than `reports/pr-<PR_NUMBER>-review.md` (and the `reports` directory itself).
- Avoid shell commands; use direct file operations for the single target file only.
