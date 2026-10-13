# Choosing how much CPU to use

In **Server sharing & queue settings**, CPU allocation advice shows the detected
logical CPUs, physical cores when available, and the allowance visible to the
app. A container may have a smaller allowance than its host. Fractional quotas
are shown as fractions, not rounded up into extra cores.

- **Automatic** recommends a scoring budget from the available CPU allocation.
- **Shared server** limits scoring to at most two threads per stage.
- **Custom ceiling** lets you reduce the maximum scoring threads for new jobs.

The ceiling does not reserve cores or limit the whole application. Decoders,
other processing stages, and concurrent jobs also use CPU. Running jobs keep
their existing preference. Change a container's actual CPU allowance in Docker,
TrueNAS or your host's resource settings—not in this control.

Advice works outside TrueNAS too. It considers logical CPUs, process affinity
where detectable and readable Linux cgroup quotas. Missing information appears
as unknown. Busy CPUs or low available memory lower the recommendation. Physical
core information is optional; virtual machines may not expose physical topology.

For one active conversion, an allowance of up to eight CPUs is a starting point,
not a universal optimum. The current scoring choices remain bounded to one, two
or four threads; a larger custom ceiling cannot enable an unqualified fast path.
Other resource checks can still choose fewer threads. Quality thresholds, frame
coverage and preservation checks do not change.

The full AV1 test reduced scoring from about 74 to 37 minutes with identical
scores across 145,943 frames. The shared workflow now includes that four-thread
scoring option when the existing CPU, RAM and pressure checks allow it. This
does not change AV1 decoder threading or enable new HDR paths. These changes
are not deployed yet. Recommendations are resource-based advice, not an
automatic benchmark of the user's machine.

## Responding to other applications

The queue keeps checking CPU, GPU, RAM and storage pressure. More jobs start only
within your selected queue profile and after sustained headroom. Scoring threads
are selected when a stage starts; FFmpeg does not change that pool mid-stage.

On Linux in a dedicated container, the app can estimate competing CPU load from
host and app CPU counters. Ten seconds of high host CPU use with substantial
external activity holds new starts and temporarily pauses supported owned media
stages. They resume after 60 seconds of stable headroom. MuxMender's own high
CPU use alone does not trigger this pause.

GPU yielding still uses the existing user-enabled, ownership-aware monitor.
CPU and GPU requests share one pause lease: clearing one cannot override the
other. A missing or expired lease releases a pause; cancellation and shutdown
resume an owned stage before terminating it. Other applications are never
signaled. Pausing does not free RAM or VRAM, so memory pressure still limits
admission rather than being treated as solved by a pause.

Native installs without reliable per-app accounting retain stage-start budgets
and queue admission checks; they do not claim mid-stage CPU yielding. Windows
does not use Linux suspension. No host-wide limits or container settings are
changed. Isolated Linux qualification passed 27 checks, including generated
video frame-hash equality after a CPU-triggered pause, cancellation while paused,
lease expiry, and supervisor-death cleanup. Additional regression checks ensure
clearing CPU pressure cannot clear an active GPU pause. Real competing-app load
and final packaged-image checks remain release qualification limits.

The combined Linux integration run completed 114 tests: 109 passed and five
browser-script tests were skipped because Node was absent there. Those five
also passed separately on the development host. The first integration attempt
used a 1 GiB temporary filesystem, which correctly blocked queue starts under
the existing 12 GiB scratch-space guard. The test runner now uses its dedicated
research workspace; the production storage guard was not changed. An import
path and a stale restart-test mock were also corrected before the successful run.
