# TA Optimize · Unreal performance graph

`TA Optimize` is the local technical-art/performance workbench. It displays
Unreal-originated frame samples as a frame-time track against the selected FPS
budget, filters by stress scenario/session/profile, summarizes p95 and mean
frame time and hitches, and raises explicit optimization hypotheses for review
in Unreal Insights. Reports preserve the build ID, session, scenario, samples,
metric summaries, and `qa_status: UNASSERTED`.

## Stress scenarios

| Scenario | Phases | Signals to capture |
| --- | --- | --- |
| Steady state | warmup, steady | frame time, game thread, render thread, GPU, process memory |
| GPU pressure | warmup, steady, spike, recovery | frame time, GPU, draw calls, GPU memory |
| Actor density | warmup, steady, spike, recovery | game thread, render thread, draw calls, frame time |
| Streaming and memory soak | warmup, soak, recovery | process/GPU memory, streaming pool used/budget |
| Level traversal | warmup, steady, spike, recovery | frame time, FPS, memory, streaming pool |

The scenario selector documents the capture protocol; it does not generate load
inside Unreal. Run the corresponding developer-authored in-game scenario, emit
`performance_sample` events to the local bridge, then load its session in the
Studio tab or call MCP `get_unreal_performance_report`. Samples with another
scenario ID are filtered out. An imported JSON export is analyzed read-only and
does not get written into the game database.

## How to read the graph

The graph plots the selected metric by event sequence and shades contiguous
sample phases (`warmup`, `steady`, `spike`, `recovery`, `soak`). Spike-phase
segments use an amber trace; phase labels come from the Unreal event payload,
not inferred thresholds. Specify one candidate
session ID to prevent mixing runs; an optional baseline session compares the
same profile, scenario, and FPS target and reports signed mean/p95/max deltas.
The dashed amber line is
the frame budget (`1000 / target_fps`) when viewing frame time. A frame over
twice that budget counts as a hitch. CPU/GPU dominant-thread comparisons and
memory/streaming changes are diagnostic leads, not root-cause proofs. Compare
the same profile, build, scenario, resolution, quality settings, and session
duration before attributing a change to an optimization.

## Current integration boundary

The repository contains the receiver, typed sample validator, SQLite storage,
analysis, graph, and report export. No Unreal `.uproject`, C++ plugin, Blueprint
instrumentation, or game build is present in the workspace. Therefore the
feature cannot run a genuine game stress test or report actual Little Nightmares
or HighSchoolBlood performance until an instrumented Unreal build emits the
documented events. Studio never substitutes its own desktop FPS for game FPS.

## Platformer profile: Little Nightmares style

The `little-nightmares` profile expects the user to launch the game; the
executable path is intentionally not guessed. Its `platformer_stealth` strategy
requests discrete actions and grounding around footing, landing zones, ledges,
patrols, hiding, falls, and checkpoints. The catalog includes traversal and
stealth cases. These remain drafts until the game has a repeatable save/checkpoint
and an approved visual or Unreal state oracle for grounded, hidden, detected,
dead, and checkpoint states. The agent must not turn a visible screen change
into a pass assertion.
