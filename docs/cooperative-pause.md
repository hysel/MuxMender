# Temporary resource yielding (experimental)

MuxMender's shared native stage runner can temporarily pause its own Linux
media workers. It leaves the supervisor and dashboard running, reports the
pause reason, and excludes suspended time from that stage's runtime and stall
limits. Resuming clears the old speed estimate. Cancellation remains active.

The next app has an opt-in **Yield GPU to other apps** control under Resource
settings. It is off by default and requires a trusted read-only host telemetry
feed. The existing queue pause still means "finish active jobs, then wait."

The controller blocks new starts as soon as outside GPU work is measured. After
five seconds of sustained outside activity it suspends supported stage workers.
It resumes after 60 seconds of quiet. Idle memory allocations alone do not cause
a pause. Missing/stale ownership data is reported explicitly: new starts wait,
and active workers are released rather than suspended indefinitely.

## Research control

For an isolated research invocation, set `MUXMENDER_PAUSE_LEASE` to an absolute
JSON file path in its private writable work directory. The controller must
atomically refresh a request such as:

```json
{"pause": true, "expires_at": 1900000030, "reason": "Other GPU work"}
```

`expires_at` is a Unix timestamp no more than 60 seconds in the future. Refresh
it while yielding; remove the request or let it expire to resume. Malformed,
missing, expired, and overlong requests do not suspend workers. Keep the path
private to the trusted controller; it is not a public API or a source path.

Only direct media-tool children launched in their own process session are
eligible. External GPU process IDs are never signal targets. Windows is not
supported. Python orchestration is deliberately not suspended because it has
its own watchdogs.

## Limits and remaining qualification

- GPU memory stays allocated; queued device work may finish after suspension.
- This does not survive a container/server restart. A Linux parent-death signal
  kills the directly owned media worker if its supervisor dies, including while
  suspended. Existing interrupted-job recovery applies; no checkpoint is implied.
- Only `native_pipeline.stage` participates. Other subprocess runners and outer
  deadlines need integration before enabling this for whole jobs.
- Qualification still needs long-duration/HDR filter workloads and broader
  repeated-pause coverage. Short SDR GPU tests do not certify every media path.
- External activity detection needs reliable ownership mapping across container
  PID namespaces. An app holding VRAM alone is not evidence of active contention.
- Admission blocking, cooldown, saved settings and dashboard status use the shared
  policy. Installing the host monitor is a separate, explicit administrator action.

No quality, metadata, savings, publication or cleanup rules are relaxed.

## Evidence so far

On Linux, 41 targeted pause/stage/runtime tests pass, including expiry,
timeout exclusion, cancellation during suspension and isolated process ownership.
A generated three-second video/audio mux was suspended after processing began
and resumed successfully. All 171 packet payload hashes, timestamps, durations,
sizes and stream indices matched the source. This qualifies that small mux case,
not GPU encoding, every container format or whole-job automatic yielding.

Additional RTX 5050 generated SDR tests passed for H.264, HEVC and AV1 NVENC.
For each codec, the paused/resumed four-second output matched the uninterrupted
baseline's 96 decoded frames and timestamps exactly. The fixture verifier needed
an explicit two-thread limit on this shared host; the initial verifier attempt
failed before any paused GPU comparison and was not counted as a pass.

The expanded Linux suite ran 74 tests: 72 passed and two existing platform tests
were skipped. Coverage includes process ownership/PID reuse, stale telemetry,
admission and settings, cooldown, cancellation, stage timeout exclusion and
death of a supervisor while its worker is suspended. UI control JavaScript passed
syntax checking. Live host-monitor-to-production-app qualification is pending;
the production queue and app have not been changed.

## Host monitor setup

Use the [bundled installer](gpu-monitor-setup.md). It includes the collector,
registers automatic TrueNAS startup, and uses a directory that survives normal
reboots. This remains a host installation step because ownership measurement
needs the host process namespace.

Run `python/gpu_activity.py` on the **TrueNAS host**, where NVIDIA PIDs and `/proc`
refer to the same processes. Do not run the collector in an isolated PID namespace
and assume numeric PIDs are interchangeable. The collector exports GPU UUIDs,
process names, PID-namespace identity, start ticks and utilization only. It never
signals a process, reads media, or accesses the Docker socket.

Use an administrator-owned script and private output directory. Cross-user
process namespace inspection may require a privileged, restricted service. Do
not make that script or directory writable by app users. Start it under a service
supervisor so it survives shell disconnects:

```sh
python3 /administrator-owned-path/gpu_activity.py --output /private-monitor-directory/activity.json
```

Mount that **directory** into MuxMender read-only (not a single file: updates use
atomic replacement), for example at `/gpu-telemetry`. Set
`MUXMENDER_GPU_TELEMETRY=/gpu-telemetry/activity.json`. Then enable the UI control.
Confirm it reports current telemetry before relying on automatic yielding. No
Docker socket, write access to other apps, or control of Plex is required.
