# Control UI: folder / video requests

This update is staged, not deployed automatically. It retains the established
dashboard design and adds a source browser, exact-file preview and serial job
queue. There is no delete, overwrite, replace-original, arbitrary-command, or
software-install endpoint.

## One-time deployment

Wait for running jobs to finish. In the TrueNAS administrator shell:

```sh
sudo docker build -f /mnt/FR4G/Apps/muxmender/app-build-20260918-v5/deploy/truenas/Dockerfile.app \
  -t muxmender-app:20260918-v5 /mnt/FR4G/Apps/muxmender/app-build-20260918-v5
```

Edit the existing app:

- Image tag `20260918-v5`, same repository, pull policy Never.
- `MUXMENDER_CONTROLS_ENABLED=true` (opt-in; otherwise endpoints stay absent).
- `MUXMENDER_QUEUE_ENABLED=false`: the old season-scanning queue stays disabled.
- Clear `MUXMENDER_SOURCE`; do not run a one-shot worker alongside UI requests.
- Keep `MUXMENDER_PLAYBACK_CODECS=hevc,av1`, the existing GPU assignment,
  UID/GID, password, allowed hosts, port and folder mounts.
- `/media` must remain read-only; `/output` writable and separate.

Refresh the browser once. Use the existing private-LAN dashboard URL and
credentials. No media is queued automatically by deployment. Old job history
remains visible; the previously completed autonomous queue is not resumed.

## Workflow

1. Browse the mounted media root or enter a relative path / `/media/...` path.
   Windows `Y:` and browser-local files are not server paths. Select one video
   or a folder, optionally including subfolders. Maximum 100 videos/request.
2. Choose Analyze, Test samples, Encode safe copies, or Keep original.
3. Select automatic HEVC/AV1 comparison or one codec; hardware auto/NVIDIA/AMD/
   Intel; automatic balanced/compact comparison or one quality preset; minimum
   savings 10–90%. These choices cannot lower the quality floors.
4. Preview the exact file list and settings, then Confirm and queue. Editing a
   setting invalidates the preview; previews expire in ten minutes. Source
   changes between preview and processing are rejected.
5. Monitor Selected jobs and the existing detailed job cards. Analyze-only
   plans and worker failures are available through View log / analysis.

Analyze probes without encoding. Test compares short samples, without creating
a full copy. Encode first tests and selects, then validates a full copy only
when the measured gates pass. Keep records a no-conversion decision. Selecting
the same file with a different mode/settings is allowed; exact duplicate
requests are suppressed unless previously failed/interrupted.

All modes retain sources. No resizing, frame-rate conversion, cropping or
tone mapping is enabled. Measured automatic conversion currently accepts only
the existing progressive 8-bit BT.709 SDR eligibility rules; unsupported HDR,
Dolby Vision and other inputs are blocked. CPU fallback and H.264/VVC/VP9
production conversion are not offered by this UI version. Requested GPU
encoders must pass the actual runtime probe; vendor selection is not a promise
of support. Codec choices must be declared playback-verified in app settings.

## Safety and limitations

Authenticated same-origin POSTs require a per-process CSRF token and bounded
JSON bodies. The server resolves paths inside the media mount and rejects
symlinks / parent traversal. No shell is used for worker commands. Queue state
is durable in `/output/ui-requests/requests.json`. Linux locking prevents a
second UI worker. Do not launch manual encodes concurrently: external tracked
jobs are checked, but manual shell launches cannot be made atomic with the UI.

Pause waits for the active job, then stops new starts. Resume continues pending
work. Two processing failures pause the queue; a restart marks an interrupted
job for review and pauses pending work. No automatic retry or media cleanup.
Free-space reserve is at least 12 GiB and three times the next source size.
Eligibility errors are per-file failures; review their log before resuming.
The existing basic authentication is for a trusted private LAN, not public
Internet exposure. Original replacement remains a separate explicit approval.

The UI lists the latest 100 request entries; older request records remain on
disk. Browser rendering and mocked workers are tested; real browser/GPU
verification of this release requires deployment. No source was converted or
changed while implementing the UI.
