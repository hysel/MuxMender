# Keeping validation moving

Heavy checks now wait in arrival order. A newer check cannot jump ahead of a
waiting one. If a worker exits, its operating-system lock is released and its
abandoned queue ticket can be reclaimed. Media files are never used as locks.

One heavy check remains the normal limit. A second can start after at least
30 seconds of measured headroom: 12 available CPU cores, CPU usage at or below
50%, 12 GiB available within the allocation, 16 GiB available on the host, low
memory and storage pressure, and a sufficiently idle, cool GPU with 4 GiB free.
Missing measurements keep the limit at one. These are initial admission settings
to test on the shared host, not a promise of twice the throughput.

When pressure rises, running checks finish normally. New checks wait until the
lower limit can be respected. Waiting does not consume the user's processing
time limit; cancellation remains available. Quality, metadata, timing, and
savings checks are unchanged.

The policy is shared by the CLI and app when a validation lock root is configured.
Older workers retain compatibility with the first lock, but should be drained
before deploying if strict arrival ordering is required across the transition.

## Next qualification steps

New jobs use timing schema 3: admission waits are measured separately from frame
validation and quality measurement, even when progress labels change. Nested
operations do not double-count elapsed time. The dashboard refreshes these
counters with job heartbeats. Legacy jobs cannot provide this separation and
are labeled accordingly. Native-stage cooperative GPU-sharing pauses have a
separate counter in schema 3; schema 2 included those in operation elapsed time.
Neither format should be presented as CPU-active time.

The next build separates CPU validation from a shared GPU lane for NVIDIA
encoding and GPU quality filters. Each has one slot by default, with a second
after sustained headroom. CPU-only quality filters remain with CPU validation.
Publication uses a separate single slot so large final copies do not compete
with each other. Every publication check remains inside that admission boundary.
All lanes use the same cancellation and abandoned-ticket recovery mechanism.

The whole-job ceiling and existing free-space admission checks are unchanged:
this does not create an unbounded backlog of encoded files. GPU-sharing leases
block new GPU stages, and in-flight cooperative suspension remains active.
These limits are shared-host safeguards, not a measured throughput claim.
Compare complete job times and application responsiveness before increasing
concurrency further. Drain old workers before deploying to avoid mixed policy.

- Measure whole-job throughput and host responsiveness with the new admission
  policy; unit tests are not performance certification.
- Source frame and copied-track evidence already have reuse within a run.
  Durable reuse across retries is not enabled by this change. It needs complete
  evidence, source and evidence identity checks, tool/policy compatibility, and
  a bounded retention policy that does not defeat work-file cleanup.
- The experimental faster HDR reader is not enabled. Section comparisons are
  promising, but complete-file and known metadata-loss regression qualification
  are still required.
- Resume checkpoints must never turn a partial encode or incomplete validation
  into a publishable result. Publication still requires all existing checks.
