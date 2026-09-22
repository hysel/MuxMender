# MuxMender 20260920-v34

- Temporary automatic-conversion skip for every detected Dolby Vision source,
  including combined Dolby Vision + HDR10+. Explicit reason appears in Results;
  originals remain untouched and no GPU trial starts for header-detected DV.
  HDR10/HDR10+-only and HLG retain existing validated paths. This does not enable
  the separate experimental DV route.
- Source-proven complete-GOP reference recovery fixes excessive Timing case A
  preroll without relaxing duration, quality or timing validation.
- HDR finalization preserves original non-video packets and block durations;
  fixes Timing case C timing reconstruction and AC3 tail-duration loss.
- Lifetime savings and CPU/GPU/RAM panel at top; clear queue waiting reasons;
  HDR prefix quality uses explicit stage names and known frame-count progress.
- File failures no longer trigger the repeated-failure automatic pause. Manual
  pause, cancellation, disk/resource safeguards and publication checks remain.

TrueNAS isolated qualification passed Timing case A and Timing case C. Timing case C's sample
was 8.666% smaller, with common-render VMAF mean 94.195 and p5 92.667; these
are sample screening results, not a full-file savings or perceptual guarantee.
Generated AAC/AC3/EAC3/TrueHD, fractional-rate/B-frame and subtitle/offset tests
passed. Automatic stale standalone-job recovery remains future work.

Build (staged context; no Git checkout needed):

```bash
sudo docker build \
  -f /mnt/FR4G/Apps/muxmender/app-build-20260920-v34/deploy/truenas/Dockerfile.app \
  -t muxmender-app:20260920-v34 \
  /mnt/FR4G/Apps/muxmender/app-build-20260920-v34
```

Change the existing app image tag to `20260920-v34` and redeploy, retaining
mounts, user IDs and settings. Confirm the version, then resume pending work
if paused. Previous failed/skipped jobs require explicit retry/re-add; they
are not silently requeued. No restart, queue resume or source change is
performed by packaging this release.
