# UGAF Telemetry plugin (experimental)

Optional Unreal Engine runtime component that sends read-only frame-time windows to the UGAF Studio localhost receiver. It does not send input or change game state.

## Install in a game project

1. Copy `UGAFTelemetry` into `<Project>/Plugins/`.
2. Regenerate project files if needed, build the Editor target, then enable **UGAF Telemetry** in the project Plugins panel and restart the editor.
3. Add one `UGAFTelemetryComponent` to an actor that stays alive for the measured level/session. Multiple components create independent sequences and should not share one bridge session.
4. Set `Profile`, the exact `BuildId`, `SceneId`, `ScenarioId`, and `Phase` in the component details. Valid phases are `warmup`, `steady`, `spike`, `recovery`, and `soak`. A Blueprint may call `SetScenario` when a scenario phase changes.
5. Start the UGAF receiver with the same profile/build and a session ID. Launch the game process from an environment that contains `UGAF_UNREAL_BRIDGE_TOKEN` (at least 24 characters), for example from the same PowerShell session as the receiver.

The component posts once per sample interval (default one second) to `http://127.0.0.1:8766/v1/events`. The `frame_time_ms` value is the nearest-rank P95 of frames captured in that interval; `fps` is its reciprocal. `memory_mb` is the Unreal process physical-memory usage sampled from `FPlatformMemory::GetStats()` at send time. The component does not yet report CPU/GPU timing, draw calls, or streaming-pool counters. It silently skips a sample if the token/config is missing, and does not retry failed HTTP requests.

## Scope and verification

The plugin compiled successfully with Unreal Build Tool in a temporary C++ host project using Unreal Engine 5.7. That confirms the plugin source builds against UE 5.7; it does not verify integration with the target game's project, exact engine configuration, runtime loading, or telemetry delivery from a game. The repository still does not contain the target `.uproject` or source. Verify it in that project before using it for performance acceptance. Use Unreal Insights for CPU/GPU attribution; this component is a lightweight trend sampler, not a replacement profiler.
