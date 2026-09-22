# MuxMender 20260920-v33

## Included since v32

- Shared NVIDIA generation hints, real source-format initialization checks and
  positive probe caching keyed by GPU/driver/FFmpeg/format. Unknown generations
  are probed, not blocked. Multiple GPUs are not assigned generation assumptions
  or cached default-device results. No multi-GPU scheduling added.
- Top-of-page processing dashboard: named workflow steps, per-check progress,
  compact active-job cards and explicitly scoped ETA; no invented overall %.
- Setup folds after successful nonempty queue submission; keyboard focus moves
  to its visible summary. Results search/filter/sort controls can fold too.
- Shared automatic CLI/app arguments and shared naming helpers; cryptic names
  can use an unambiguous descriptive folder name. Collision and companion-file
  protections remain in place.
- Automatic generated-artifact cleanup after durable verified replacement.
  Published target hash/size must match the receipt before cleanup. Original
  media, receipts, summary evidence and logs are not cleanup targets. Cleanup
  errors are reported separately from successful publication.
- Shared DV qualification/quality measurement helpers. Dolby Vision automatic
  conversion is NOT certified or enabled by this release; the NVIDIA DV matrix
  is still a separate test. Combined Dolby Vision/HDR10+ remains unqualified.

No mount, authentication, GPU assignment or quality threshold change is required.
Existing job settings and replacement authorization still apply. New code takes
effect after app restart; do not restart during the standalone DV test.

## Build (does not restart the running app)

```bash
sudo docker build \
  -f /mnt/FR4G/Apps/muxmender/app-build-20260920-v33/deploy/truenas/Dockerfile.app \
  -t muxmender-app:20260920-v33 \
  /mnt/FR4G/Apps/muxmender/app-build-20260920-v33
```

After the independent test finishes, set the TrueNAS app image tag to
`20260920-v33` (repository stays `muxmender-app`). Keep current mounts, GPU
assignments and settings. Confirm the displayed version and queue state before
resuming work. Do not remove the previous image until startup is verified.

## NVIDIA preflight after deployment

```bash
sudo docker exec ix-muxmender-muxmender-1 \
  python3 -B -m encoder_capabilities --execute
```

This uses four synthetic frames per detected/listed encoder, not user media.
It is an initialization check, not complete SDR/HDR/DV or playback qualification.
Real source trials continue to determine savings and quality eligibility.

## Test scope

Regression coverage includes shared CLI/app parity, cache invalidation, old and
missing NVIDIA telemetry, transient errors and results disclosure structure.
Hardware behavior on other NVIDIA generations still needs physical-card tests.
