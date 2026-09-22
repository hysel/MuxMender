# TrueNAS v31 — automatic HDR preservation and MP4 timing

Version: `20260919-v31`.

## Implemented

- The normal queue now admits PQ/HDR10/HDR10+ and HLG into measured trials.
  HDR is no longer unconditionally sent to a standalone-review result.
- HEVC trials invoke the integrated finalizer: restore HDR10+ when present,
  reconstruct original video timestamps, copy original companion tracks and
  chapters, and validate the completed output. Source-driven dimensions,
  pixel format, aspect ratio, chroma positioning and color properties remain
  checked. No output resizing or tone mapping is introduced.
- AV1 is tested on the assigned hardware and evaluated on actual preservation,
  quality and size. A failed AV1 candidate does not block HEVC. Intel AV1 can
  reach these checked trials rather than being rejected before encoding.
- The main image includes MKVToolNix and the checksum-pinned HDR10+ tool. No
  separate preservation image or manual finalization is needed for these jobs.
- HDR quality uses identical fixed HDR-to-SDR rendering for both metric inputs,
  followed by VMAF mean/fifth-percentile floors of 90/90. This is explicitly a
  rendered-view proxy, **not a native-HDR quality model or a percentage of
  retained visual quality**. Output video stays HDR. Native metadata/timing,
  copied track payloads and full decode are verified independently.
- MP4 timestamps use the demuxer time base during encoding. This fixes the
  fractional-start/frame-rate quantization which shifted a tested timeline
  approximately 11 ms. The existing 2 ms validation tolerance is not widened.
- Adaptive NVENC trials prioritize CQ20/18 when quality is the limiting factor,
  instead of exhausting the shared retry budget on smaller/lower-quality
  settings first. Size-limited cases retain the size-oriented search order.
- Old HDR admission failures may be retried after an app update when that
  folder is submitted again. This does not automatically submit new jobs or
  override completed conversions/explicit keep decisions. Execution version is
  recorded separately from request creation version.
- Source frame evidence is reused within the same guarded HDR workflow instead
  of decoding the full source twice. Successful native validation removes only
  that run's registered temporary HDR bitstreams and encoder intermediates;
  originals, final candidates and validation reports are retained.
- HDR helper processes honor cancellation/source-change/disk guards while
  running, not only before and after a potentially long command.
- Streaming checks both final process exit statuses after draining the pipes.
  A last-moment producer failure cannot be hidden by an earlier success message.

## Verification

- 494 unit/regression tests pass on Windows and TrueNAS host Python, with 3
  platform-dependent skips on each. Container/GPU qualification is separate.
- Generated automatic PQ HEVC/AV1 trials, selection, full copy and validation
  pass. A separate HEVC-only test covers the full finalization/cache route.
- Generated HLG HEVC trials and full-copy validation pass.
- These orchestration fixtures use mocked CPU encoder substitutions and relaxed
  metric floors **only in test code**, not production settings or GPU claims.
- A fractional-start MP4 fixture reproduces the old timing failure. The new
  command passes all 48 frames without loosening the timing tolerance.
- Actual HDR10 excerpt: 292 frames pass metadata, timing, companion tracks and
  decode. Rendered source/self mean 99.24, p5 98.74. Encoded pair mean 87.02,
  p5 79.95: correctly rejected by the production 90/90 quality floors. This is
  evidence for trying better settings, not grounds to bypass quality checks.
- Actual HDR10+ excerpt: stripping dynamic metadata from a generated bitstream
  and restoring it through the integrated finalizer passes all 202 frames with
  exact HDR10+/static metadata and timestamps, copied tracks and full decode.
  The file on Y: is only read. This is a restoration test, not a quality trial.

## Deployment and remaining verification

The v31 build context is staged separately; the running app is not modified by
staging. Build it, then select the new tag in TrueNAS:

```bash
sudo docker build -f /mnt/FR4G/Apps/muxmender/app-build-20260919-v31/deploy/truenas/Dockerfile.app -t muxmender-app:20260919-v31 /mnt/FR4G/Apps/muxmender/app-build-20260919-v31
```

New RTX 5050 automatic HDR trial results require deployment; local fixtures do
not certify the deployed driver/encoder. Existing user settings and replacement
authorization remain in effect. The app still requires strictly smaller output
and successful validation before an authorized replacement.

Dolby Vision RPU integration, interlaced processing, rotated video and unusual
multi-video layouts are not claimed solved by this release. Missing or changed
HDR metadata, corrupt streams, actual frame loss, insufficient quality, larger
outputs and destination conflicts still prevent replacement with a recorded
reason. No source media is replaced or deleted to build or test this release.
