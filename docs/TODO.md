# MuxMender roadmap

## Completed and accepted

- [x] Consolidate runtime, design, PowerShell helpers and documentation into their
  dedicated folders; keep shared behavior in existing modules.
- [x] NVIDIA actual HEVC/AV1 tests and full SDR/DV playback validation on the tested
  Windows setup, including the repaired ordered mux and seeking path.
- [x] Intel Arc B580 SDR HEVC/AV1 and HEVC HDR10 full-file checks and client review.
- [x] Intel AV1 HDR10 metadata repair and HEVC DV Profile 8.1 full-file validation;
  Chrome/Sony TV and Y-backed playback approved for both new full outputs.
- [x] Integrate AV1 HDR through mandatory full verification and opt-in Intel DV
  through the standalone CLI. 193 unit tests and three actual CLI regressions pass.
- [x] Preserve control-room design; stationary progress bars, stage-specific ETA,
  recent-rate measurement, and stale-job handling.
- [x] Ordered mux memory guard; sparse/empty-subtitle stress, source frame timing,
  original track and chapter preservation, full decode and seeking checks.
- [x] Preserve release suffixes in optional video/sidecar rename plans. Renaming is
  preview-first, no-clobber, journaled, and checks identities before applying.
- [x] Optional NFO/sample cleanup plans with explicit confirmation; protect main
  video and all subtitle files, including subdirectories. Never infer sample
  eligibility solely from duration.
- [x] Optional video-only output folders; exclude work data from later media scans.
- [x] Per-run savings in decimal MB/GB/TB and percent, distinguishing accepted size
  reduction from actual space reclaimed when originals/intermediates remain.

Current support and evidence: [HARDWARE.md](HARDWARE.md).
Handoff and media permissions: [NVIDIA-HANDOFF.md](NVIDIA-HANDOFF.md).
Historical failed experiments are retained in local reports, not pending tasks.

## AMD regression (next hardware work)

- [ ] Re-test RX 7800 XT with the newer shared mux, memory, subtitle and seeking
  fixes: generated fixtures, separate real sample, then full-file regression.
  Prior evidence is one Profile 8.1 episode, 53.7% smaller, with Sony DV playback.
- [ ] Check exact dimensions, bit depth/color/HDR/RPUs, original tracks, frame
  timing, decode, seeking, speed and savings; obtain intended-client review.
- [ ] Reconcile older AMD runs against retained evidence rather than restarting
  stale PIDs. In particular, inspect `reports/run-20260904-222603-65c86ac2.log`
  and `test-output/stream-full-20260904-222606-dbe340ac/` if available.
- [ ] Broaden AMD HEVC/AV1 SDR/HDR coverage across GPUs, drivers and operating systems.

## Metadata enrichment

- [ ] Add an optional shared provider lookup for BOTH Plex library metadata and
  generated-file tags, exposed through existing standalone commands.
- [ ] Default off; fill missing ratings, dates, descriptions, genres and artwork
  where supported. Preserve user edits and record provider/retrieval date.
- [ ] Resolve ambiguous movie/episode identities before applying metadata. Explicitly
  configure credentials and Plex access; report unsupported container fields.
  No metadata lookup or writes are currently implemented.

## Broader compatibility and fidelity

- [ ] Expand capability-based tests across older/newer NVIDIA, Intel and AMD GPUs,
  drivers and multi-GPU configurations. Test actual encode/decode independently;
  never infer support from listed encoders or a particular model name.
- [ ] Broaden mixed audio/subtitle, unusual cadence, HDR and Plex client coverage.
  Distinguish working native playback from Plex subtitle burn-in/transcode behavior.
- [ ] Exercise missing dependencies, hardware failure, stalls, cancellation,
  restart/recovery, disk pressure and permitted CPU fallback across platforms.
- [ ] Research DV Profile 5 color-aware preservation and Profile 7 enhancement
  layers separately; do not silently discard layers or convert them to Profile 8.1.
- [ ] Keep HDR10+ and unsupported dynamic metadata blocked until separately proven.
- [ ] Review representative scenes for quality and size. Do not use metadata or
  decode success as proof of identical visual quality. Larger outputs are rejected.
- [ ] Extend the browser workflow beyond its current validated SDR queue only after
  equivalent approval, validation and recovery behavior is implemented and tested.
- [ ] Broaden browser visual QA while retaining the approved control-room design.

## TrueNAS / Linux

- [ ] Confirm target edition/version, CPU, RAM and available GPUs.
- [ ] Package standalone execution with source datasets read-only and separate
  writable output datasets. Use local dataset paths rather than SMB on the host.
- [ ] Validate GPU exposure and FFmpeg compatibility without implicit installations.
- [ ] Provide a Linux-compatible DV color backend where needed; Windows Direct3D
  code cannot run unchanged on Linux.
- [ ] Test permissions, exclusive publication, cross-dataset hard-link restrictions,
  disk reserves, cancellation and recovery on the actual deployment.
- [ ] Profile decode, color conversion, GPU transfers, pipes, encoding and storage
  before making performance promises.

## Standing product constraints

Standalone script first; no editor dependency or unsolicited reload/new window.
Exact resolution by default. Source deletion/overwrite disabled; any one-time
manual replacement or cleanup needs its own authorization. No automatic driver
or software installation/update. Ask before Git operations unless the current
session already authorizes them. Preserve release labels needed by subtitle tools.
