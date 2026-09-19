# Optional validated replacement

Keep-original copy mode remains the default. New Replace action requires a separate
checkbox confirmation on the exact preview. Only full validated MKV output qualifies:
sample checks alone never authorize publication. Non-MKV sources use safe-copy mode.

Source and output hashes are compared to validation evidence. Copy is staged beside
the source and verified, an exclusive hard-link backup is made, then publication is
atomic. The backup is removed only after final hashing. Existing staging/backup files
block retry. After an interruption inspect replacement.json and recovery files before
manually retrying; no automatic recovery or deletion is attempted. Source ACL/metadata
copying uses copystat; confirm destination permissions meet your dataset requirements.

The original filename stays unchanged even if it mentions the former codec. The
validated output remains in /output. GB totals describe reduction in the source
library, not net pool free space; retained copies/snapshots still occupy space.
Totals cover replacement jobs recorded by this UI, not earlier manual replacements.

## TrueNAS deployment

Wait for jobs to finish; build:

```sh
sudo docker build -f /mnt/FR4G/Apps/muxmender/app-build-20260918-v11/deploy/truenas/Dockerfile.app -t muxmender-app:20260918-v11 /mnt/FR4G/Apps/muxmender/app-build-20260918-v11
```

- Image tag: `20260918-v11`.
- Keep existing `/mnt/FR4G/Media` -> `/media` mount READ ONLY.
- Add `/mnt/FR4G/Media` -> `/media-replace`, READ/WRITE.
- Set `MUXMENDER_REPLACEMENT_ENABLED=true`.
- Set `MUXMENDER_REPLACEMENT_ROOT=/media-replace`.
- App user 3005 needs write/delete rights on the intended media directories.
- Keep output mount, GPU and ports unchanged. Without these settings replacement
  fails closed; normal copy jobs continue working.

There is no dashboard login. Anyone who can reach it can request permanent
replacements once enabled. Restrict access to trusted users/network; never expose
it publicly. Source write access is an explicit administrator opt-in.
