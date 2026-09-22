# TrueNAS v29 — encoding progress and HDR preservation diagnostics

Version: `20260919-v29`.

## Changes since v28

- Shared FFmpeg watchdog activity recognizes increasing frame counts even when
  mux timestamps are N/A. Applied to automatic/native, CLI, streaming and NVIDIA
  test paths. Repeated values do not reset the watchdog; runtime limits remain.
- Increasing timestamps remain activity after a duration estimate reaches 100%.
- Invalid/sentinel timestamps no longer imply completion. Missing percentage is
  reported honestly with frame-count feedback; JSON HDR probes report progress.
- Unsupported-input jobs link their eligibility evidence and report skipped.
- HDR inspection distinguishes observed HDR10+, Dolby Vision and HLG, without
  claiming a sampled absence of dynamic metadata proves static HDR throughout.
- Added explicit, vendor-independent HDR10+ safe-copy finalizer and strict frame
  validator. Checks metadata, timing, geometry, progressive frames, copied tracks,
  and decoder errors. Missing runtime dependencies produce an explicit error.
- Runtime modules are included in Python installation packaging.

## Important boundaries

Automatic HDR/HDR10+ queue conversion is NOT enabled by this release. The full
NVIDIA HDR case A test used the separate preservation package,
passed 138,510-frame preservation checks and user visual review, then was manually
replaced with explicit approval. This single test is not a generic HDR quality
evaluator. The main app image does not install the standalone preservation tools.
The standalone package remains available separately with those dependencies.

The four 4:4:4 series 10-bit 4:4:4 sources and remaining legacy MPEG-4 / Dolby Vision
cases still need their specialized validation paths. No quality floors are lowered.

## Deployment

Build using an account with authorized Docker access:

```sh
sudo docker build -f /mnt/FR4G/Apps/muxmender/app-build-20260919-v29/deploy/truenas/Dockerfile.app -t muxmender-app:20260919-v29 /mnt/FR4G/Apps/muxmender/app-build-20260919-v29
```

Then select `muxmender-app:20260919-v29` in the existing TrueNAS app. Preserve
mounts, GPU assignment and history. Do not restart while a job is publishing.
After deployment, retry Timing case D with the existing retry-failed controls.
Building does not deploy or restart the app. The existing queue is not modified
by release packaging.
