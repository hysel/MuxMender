# Persistent processing history

The durable `/output/ui-requests/requests.json` ledger now prevents repeated work
on unchanged files (path, byte size and nanosecond modification time). Keep this
file on persistent output storage; deleting it removes these decisions. The UI's
100-request display limit does not truncate the ledger.

- Converted copies, replacements and deliberate keep-original decisions skip by
  default. Quality/savings rejections and unsupported inputs are remembered.
- Failed/interrupted runs and destination collisions remain retryable.
- Inspection/sample success does not block a later full conversion. Safe-copy
  success does not block an explicit replacement request (currently revalidates
  by rerunning rather than trusting an old output).
- Replacement records the published filename and new fingerprint, including
  MP4/AVI to MKV publication, to prevent second-generation conversion.
- Preview explains history skips; submission reports their count. Advanced
  settings includes an explicit Recheck previously processed files checkbox.
  Recheck does not bypass validation, confirmation, or active-job deduplication.
- Existing UI decisions are reused; older completed trial rejections are read
  from retained status reports. Historical manual/out-of-app replacements and
  legacy replacements lacking a post-publication fingerprint are not guessed
  or automatically imported. Renamed files are considered new. This is not a
  content-hash duplicate finder; preserving both size and timestamp can evade
  change detection.

No media is changed by installing this update. No new environment variables or
mounts are required. Deploy after active jobs finish:

```sh
sudo docker build -f /mnt/FR4G/Apps/muxmender/app-build-20260918-v15/deploy/truenas/Dockerfile.app -t muxmender-app:20260918-v15 /mnt/FR4G/Apps/muxmender/app-build-20260918-v15
```

Then select image tag `20260918-v15` in the app settings.
