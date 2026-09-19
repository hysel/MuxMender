# Retry skipped/failed files only

Advanced settings replaces the recheck checkbox with three choices:

- Use saved history (default): existing behavior.
- Retry skipped/failed files only: unchanged files whose latest matching version
  was skipped, failed or interrupted. Pending/running, successful conversions,
  explicit keep-original choices, inspection/sample successes, new and changed
  files are not selected. Earlier successful copies/replacements take precedence
  over redundant later failures for that path; renamed MKV publications are also
  protected. This is intentionally conservative for manually published copies.
- Recheck everything: explicit override for terminal history; active jobs still
  cannot be duplicated.

Preview and submit enforce the same selection, and the worker rechecks history
before starting. Existing recheck=true API clients remain supported. Conflicting
or invalid settings are rejected. No stored history is cleared, no source files
are changed by this update, and all validation/replacement confirmation stays.

v20 includes v19 legacy-color handling, v18 parallel workers, v17 savings/folder
limits, and earlier progress updates. Deploy this version directly after active
jobs drain, then resume the queue or resubmit a folder using Retry only.

```sh
sudo docker build -f /mnt/FR4G/Apps/muxmender/app-build-20260918-v20/deploy/truenas/Dockerfile.app -t muxmender-app:20260918-v20 /mnt/FR4G/Apps/muxmender/app-build-20260918-v20
```

Image tag: `20260918-v20`. No mount or environment changes.
