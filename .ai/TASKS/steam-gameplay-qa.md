# Active Task: Steam Gameplay QA

## Goal

Implement the first real gameplay QA workflow for the three selected Steam
games, while preserving the current installation smoke runner.

## Scope

- Steam game selection by App ID;
- launch and cleanup;
- startup timeout;
- screenshot after startup;
- one configurable visual assertion;
- HTML report;
- automated tests using mocked processes and temporary images/files.

## Out of scope

- game-specific mouse/keyboard automation;
- online multiplayer actions;
- modifying Steam files;
- changing the existing GUI layout beyond the minimum action needed to run QA.

## Handoff to Hermes

Read `.ai/PLAN.md` and `.ai/ACCEPTANCE.md` first. Work on a branch named
`hermes/steam-gameplay-qa`. Update `.ai/RESULT.md` when implementation and
verification are complete.
