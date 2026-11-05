#!/usr/bin/env bash
# A2A dispatcher: Hermes(Planner) -> OpenCode(Engineer)
# Planner model: opencode/hy3-free (x-preview-f-free deprecated)
# Engineer model: opencode/hy3-free (fallback lmstudio/qwen3-30b)
# Usage: bash .ai/a2a/dispatch.sh TASK-001
set -euo pipefail
TASK_ID="$1"
REPO="C:/Users/Admin/UGAFStudio"
BRIEF="$REPO/.ai/a2a/tasks/$TASK_ID.md"
LOG="$REPO/.ai/a2a/logs/$TASK_ID.log"
[ -f "$BRIEF" ] || { echo "Brief not found: $BRIEF"; exit 1; }
mkdir -p "$REPO/.ai/a2a/logs"
cd "$REPO"
opencode run --model opencode/hy3-free "$(cat "$BRIEF")" > "$LOG" 2>&1 || opencode run --model lmstudio/qwen/qwen3-30b-a3b-2507 "$(cat "$BRIEF")" > "$LOG" 2>&1
echo "EXIT=$?" >> "$LOG"
echo "Done. Log: $LOG"
