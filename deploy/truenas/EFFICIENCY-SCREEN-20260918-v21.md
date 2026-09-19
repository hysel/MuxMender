# Fast keep-original screening — v21

Includes the existing v20 app and local efficiency-screen changes:

- Compare combined bytes of three short clips before expensive VMAF validation.
- Reject-only size screening; no positive decision without existing quality,
  preservation, decode and full-file publication gates.
- Stop remaining quality checks for a setting after a confirmed failure.
- Deferred reference self-check uses requested quality floors, not fixed 98/95;
  no normalization or relaxation of conversion thresholds.
- Clearly explain already-efficient decisions for the tested settings. Persist
  these decisions for unchanged files and matching selected policy; explicit
  recheck/retry or changed policy can re-evaluate them.
- Failed/incomplete evaluations are not cached as already efficient.

Verification: 379 unit tests run, 3 skipped, no failures. Existing generated-media
integration smoke passed selection, full-copy validation and unchanged source hash.
No production media was encoded or replaced by these verification runs.

Build on TrueNAS:

```sh
sudo docker build -f /mnt/FR4G/Apps/muxmender/app-build-20260918-v21/deploy/truenas/Dockerfile.app -t muxmender-app:20260918-v21 /mnt/FR4G/Apps/muxmender/app-build-20260918-v21
```

Then edit the existing TrueNAS MuxMender app image tag to `20260918-v21`.
Repository remains `muxmender-app`. Keep existing GPU assignments, user/group,
ports, mount paths, environment and image pull policy. Do not recreate the app or
clear its output/history. Retain the old image for rollback.

Before deployment, ensure active jobs have drained, including manually launched
comparisons. The queue was paused with zero active jobs when v21 was staged;
leave it paused through deployment. No queue resume is part of this update.

After deployment, verify the dashboard/API and installed source version. To retry
older calibration failures later, use Retry skipped/failed files only. Existing
older decisions are not retroactively rewritten by the update.
