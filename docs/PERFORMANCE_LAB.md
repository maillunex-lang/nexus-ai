# Performance Lab — runtime MCP tools

Implemented in the backend, separate from the instructional plugin skill.

## Tools

- `nexus_godot_profile_start(project_id, seconds=10)` queues a bounded runtime benchmark.
- `nexus_godot_profile_status(job_id)` returns only the OAuth owner's job and measurements.
- `nexus_godot_optimize_isolated(project_id, preset="economy", seconds=10)` benchmarks a baseline, applies the trusted FPS-budget recipe in a separate copy, validates it and benchmarks again.

Execution requires owner `mcp:write`; reading results requires owner read/write. Imported inspection-only projects are rejected. The API and host worker both enforce their existing execution project allowlists. Duration is 5–60 seconds per sample, plus a two-second warmup.

## What is measured

The probe runs the project's main scene in headless Godot, with an upper harness cap of 60 FPS. It records observed FPS, p95 frame interval, p95 engine process time, peak Godot static memory and peak node count. Reported static memory is not OS RSS or total device RAM. Inputs are idle; no automated gameplay replay is provided yet. A headless timing run does not establish Android FPS, GPU performance, draw calls, overdraw, temperatures or power consumption.

The first optimization recipe applies an FPS limit (economy 30, balanced 45, high 60) using a generated autoload only in the copy. A lower cap trades frame rate for lower work; no speedup or energy saving is asserted without device measurements. Other gameplay scripts and assets are not automatically rewritten. Game code may override the cap; the report includes the effective cap at the end of sampling.

## Execution and safety

The existing flock-protected `scripts/godot_queue_worker.py` processes one performance task per invocation after its existing tasks. It uses `performance_pending/running/completed/failed` directories in the existing shared queue volume. No new listener, database migration or service is required.

Validation and runtime run in fresh workspaces with Bubblewrap network/PID/user namespaces, a restricted filesystem, CPU/log limits and a wall-clock timeout. Missing sandbox support fails the task; there is no unsandboxed fallback. The source manifest SHA is checked before and after. Changes are never copied back, published or merged. This is filesystem isolation, not protection against engine/kernel vulnerabilities. Runtime benchmark workspaces are retained like existing Godot validation workspaces; they require operator disk cleanup. Worker crashes may leave running records requiring operator recovery; automatic recovery/retry is not implemented.

## Activation

Deploy the backend plus `scripts/godot_performance_worker.py` and `scripts/godot_performance_probe.gd` together with the existing worker script. Preserve the existing project mounts, queue volume, flock and sandbox setup. Restart/reload the API through the established deployment process and refresh MCP discovery in the client. `nexus_capabilities` must then list all three tools. Merely uploading a plugin skill does not install these server tools.

This change does not deploy to Lunex. A production smoke test should queue a short profile on an explicitly execution-enabled game, poll it, test the economy copy and verify that source fingerprints match. To obtain Android graphics data, the next stage needs an instrumented device runner and reproducible gameplay scenarios.
