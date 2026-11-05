# TASK-012: Frame-diff reward channel + learn() wiring

## Goal
Give the agent a pseudo-reward signal so `learn()` becomes meaningful — the first step toward RL.

## Changes
1. New file `qa_framework/gameplay_agent/reward.py`:
   - Class `FrameDiffReward()` with `update(self, frame: np.ndarray) -> float`:
     - Keeps previous frame's visual hash (reuse `_visual_hash` from skill_cache.py — import it).
     - Reward = 0.0 on first frame; else 1.0 if hash changed (screen progressed), 0.0 if unchanged.
     - Also expose `changed: bool` attribute after each update.
2. Wire into `scripts/live_gameplay_agent.py`:
   - After dispatching each action and sleeping, grab the next frame first, compute reward = reward_fn.update(new_frame), call `agent.learn(reward, done=False)`, log "reward=...".
3. Extend `skill_trace.jsonl` entries with `"reward": <float>`.
4. Tests in `tests/test_reward.py`: first update returns 0; different frames → 1.0; identical frames → 0.0.

## Acceptance criteria
```
cd C:/Users/Admin/UGAFStudio
PYTHONPATH=C:/Users/Admin/UGAFStudio C:/Python314/python.exe -m ruff check qa_framework/gameplay_agent scripts/live_gameplay_agent.py tests/test_reward.py
PYTHONPATH=C:/Users/Admin/UGAFStudio C:/Python314/python.exe -m pytest tests/test_reward.py -q
```

## Report
End with `## A2A REPORT`.
