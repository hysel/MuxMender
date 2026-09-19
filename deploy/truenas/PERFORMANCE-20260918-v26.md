# v26 — Measured validation and reproducible releases

Includes the v22–v25 workspace, safety and validation changes. No quality gate is
lowered. Full video/audio decode, preservation evidence and verified replacement
are still required. Production GPU decoding is **not enabled** by this release.

## Measurements

`tools/benchmark_validation_pipeline.py` generated a 30-second 720x480 HEVC
output and H.264 source with three AC3 tracks and one SRT track. Three
alternating-order rounds compare automatic frame threads/per-track packet scans
with two-thread readers/combined packet scans. Both retain full decode, metadata,
frame and packet comparisons and source/output hashes.

- Legacy median: 2.041 seconds.
- Current median: 1.479 seconds.
- **Complete validation took 27.6% less time on this local fixture.**
- This is not an encode/VMAF/publication benchmark, a TrueNAS result or a claim
  that an entire library finishes 27.6% sooner. Short warm-cache tests have limits.

## Changes

- Jobs persist bounded, monotonic wall-time totals for encoding, full decode,
  frame checks, track checks, quality measurement, checksums, metadata, extraction
  and other work. Heartbeats do not double count; counters stop on completion.
  The API exposes these totals and the active progress panel shows them in an
  expandable "Where processing time is spent" section. Old jobs have no invented
  historical timing data.
- GPU telemetry reports compute, encoder and decoder load separately. Admission
  now considers decoder saturation too; unknown telemetry stays conservative.
- Fix missing Python package modules, and track only an explicit allowlist of
  development tools. Fresh clones and portable release contexts include tools
  imported by tests; no local binaries, credentials or generated media are added.
- Add generated-only full-validation and GPU pixel-equivalence benchmarks.
  The GPU experiment runs in an isolated container with no media mount/network,
  two CPUs, 2 GiB RAM, no Linux capabilities and a separate writable scratch path.
  Pixel agreement on one SDR fixture cannot certify HDR/audio/corrupt-stream
  handling or authorize switching production validation to GPU.

## Verification and rollout

428 local regression tests run, 3 skipped, no failures; wheel build and isolated
installed-runtime imports verified. Runtime changes do not modify media or
resume a queue. Existing parallel workers already overlap jobs; concurrency is
not raised beyond the shared-host governor's limits.

```sh
sudo docker build -f /mnt/FR4G/Apps/muxmender/app-build-20260918-v26/deploy/truenas/Dockerfile.app -t muxmender-app:20260918-v26 /mnt/FR4G/Apps/muxmender/app-build-20260918-v26
```

Deploy `muxmender-app:20260918-v26` only when desired. Mounts, environment, ports
and GPU assignments stay unchanged. Staging is not building or deploying.

Deferred pending evidence: GPU-assisted full validation; merging the independent
full-decode safety pass; resuming expensive stages across application restarts.
Checkpoint reuse must prove source/settings/tool/validator identity and retained
artifact integrity before it is safe for automatic replacement.
