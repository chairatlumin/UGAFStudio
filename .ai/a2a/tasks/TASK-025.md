# TASK-025: Wire MOA v2 early-exit + reward-weighted feedback into the live loop

## Goal
Integrate the new MOA v2 capabilities (`early_exit`, `update_rewards`) into
`scripts/live_gameplay_agent.py` so the live gameplay loop is low-latency
(waits for the fast primary VLM, not the slowest sub-agent) and self-tunes
its vote weights from observed frame-diff rewards.

## Context (file paths)
- `qa_framework/gameplay_agent/moa.py` — NEW MOAAgent v2 (already implemented &
  tested). Public API is back-compatible. New kwargs: `early_exit: bool = False`,
  `min_votes: int = 1`, `reward_alpha: float = 1.0`, `reward_ema: float = 0.25`.
  New method: `update_rewards({action_signature: reward})`. Helper
  `MOAAgent._action_signature` is private; prefer using the public method.
- `scripts/live_gameplay_agent.py` — `main()` builds the MOAAgent at the
  `--moa` branch (~line 645-676) and `LiveGameplayAgent.step()` runs the
  observe/decide/dispatch/reward loop (~line 402-542).
- `qa_framework/gameplay_agent/actions.py` — `Action` dataclass; `reward.py`
  `FrameDiffReward.update(frame) -> 1.0 if screen changed else 0.0`.

## Changes required

### 1. `scripts/live_gameplay_agent.py` `main()` MOA branch
- When `args.moa` is set, construct:
  `MOAAgent(sub_agents, weights=[...], early_exit=True, min_votes=1)`
  (keep the existing 3-model spec list unchanged). This makes the loop wait
  for the fast primary VLM (qwen2.5-vl-7b ~8.9s) instead of blocking on the
  slowest (gemma-4 ~67s).
- Keep `backend_errors` observability in the trace/log.

### 2. `LiveGameplayAgent.step()` reward feedback
- After computing `reward = self._reward_fn.update(next_frame)` (line 469),
  feed it back to the MOA agent when the agent is a `MOAAgent`:
  ```python
  if isinstance(self._agent, MOAAgent):
      from qa_framework.gameplay_agent.moa import _action_signature
      self._agent.update_rewards({_action_signature(executed): reward})
  ```
  (`executed` is the already-dispatched action returned by `_dispatch_action`.)
  This realizes reward-weighted voting: actions that change the screen gain
  influence over time.
- Import `MOAAgent` at top of file (it is currently imported in live_gameplay_agent.py).

### 3. CLI help text (`build_parser`, `--moa` help)
- Update the `--moa` help string to mention low-latency early-exit + reward
  weighting (keep it concise).

## Constraints
- Do NOT change the 3-model spec list or weights (1.0 / 0.6 / 0.4).
- Do NOT change `decide()` call sites — MOAAgent is a drop-in for VLMAgent.
- Keep `ALLOWED_ACTIONS` and the per-game strategy branching untouched.
- All new code must pass: ruff, ruff format, mypy, pytest (the existing
  `tests/test_moa.py` 11 tests + `tests/test_gameplay_agent.py`).
- No live run required (no game window needed); all behavior is unit-testable.
  Add a focused unit test in `tests/test_live_alternative.py` (or a new
  `tests/test_moa_live_wiring.py`) that:
  - mocks `MOAAgent` with `early_exit=True` and asserts `update_rewards` is
    called during `LiveGameplayAgent.step()` when the agent is an MOAAgent.

## Exact validation commands (must all pass)
```bat
cd C:/Users/Admin/UGAFStudio
PYTHONPATH=C:/Users/Admin/UGAFStudio C:/Python314/python.exe -m ruff check scripts/live_gameplay_agent.py
PYTHONPATH=C:/Users/Admin/UGAFStudio C:/Python314/python.exe -m ruff format --check scripts/live_gameplay_agent.py
PYTHONPATH=C:/Users/Admin/UGAFStudio C:/Python314/python.exe -m mypy scripts/live_gameplay_agent.py
PYTHONPATH=C:/Users/Admin/UGAFStudio C:/Python314/python.exe -m pytest tests/test_moa.py tests/test_gameplay_agent.py tests/test_live_alternative.py -q
```

## Report format
End the dispatch log / final message with `## A2A REPORT` and list the files
touched, the validation command outputs, and any follow-ups.
