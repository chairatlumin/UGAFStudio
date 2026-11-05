# Automatic Review Policy

## Default behavior

Codex reviews Hermes results automatically. Do not ask the user to approve
routine implementation findings, formatting issues, ordinary test failures, or
non-critical follow-up work.

If the acceptance criteria are met and no critical gate is triggered, mark the
review `AUTO-APPROVED WITH FOLLOW-UPS` and let Hermes continue.

## Critical gates — stop and ask the user

Stop only when one of these is present:

- credentials, tokens, private keys, or personal data are exposed or committed;
- destructive deletion, irreversible data migration, or cloud/external writes
  are required outside the stated task;
- security boundary bypass, unsafe sandbox escalation, or arbitrary remote code
  execution is introduced;
- a process started by QA cannot be cleaned up reliably;
- tests show a data-integrity, privacy, or safety-critical failure;
- the change materially expands scope beyond the active task.

## Non-critical handling

- Low/informational findings: auto-approve and record them.
- Medium/high functional findings: record as follow-up and continue when the
  core acceptance criteria pass and no critical gate is triggered.
- Missing real-environment evidence: mark as unverified, not as a blocker,
  unless the task explicitly requires live validation before merge.

## Approval boundary

This policy controls the project review workflow only. It does not bypass
Codex/Hermes platform safety prompts for destructive, external, credential,
or permission-changing actions.
