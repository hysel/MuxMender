# Cleanup after verified replacement (pending deployment)

The shared publisher invokes `replacement_cleanup.cleanup_replaced` only after
the durable replacement receipt is marked replaced. It rechecks the published
file size/hash, verifies validation/receipt agreement, and refuses cleanup when
recovery markers remain. Errors retain successful replacement status and record
`artifact_cleanup: needs-attention` rather than triggering another conversion.

Generated media, raw bitstreams/RPUs and `*-frames.jsonl` evidence are removed
only inside that completed run's private directory. Linked paths and multiply
linked artifacts are excluded. Source/published files cannot be cleanup targets.
JSON history, quality summaries, validation/publication receipts and logs stay.
Safe-copy outputs, failed jobs and active tests are not cleaned automatically.

The same module supports a read-only preview (omit `--execute`) or explicit
maintenance cleanup. On the TrueNAS host, `--media-root /mnt/FR4G/Media` maps
container receipt paths under `/media` to the same published files. Cleanup
receipts live in each run's `artifact-cleanup.jsonl`.

Deleted generated artifacts are not placed in trash. Published replacements
remain available; ZFS snapshots can retain deleted blocks, so removed bytes are
not guaranteed to equal immediate pool-space recovery.

## Maintenance completed 2026-09-20

Read-only API selection identified 19 completed replacement jobs. Each published
file was rehashed against its receipt before cleanup. Removed 619 generated
artifacts totaling 65,693,572,957 bytes (65.694 decimal GB) from those jobs only.
All 19 passed verification. Active work, DV qualification, media on Y:/the source
dataset, receipts, history and logs were retained. Per-file deletion journals
remain in each job's `artifact-cleanup.jsonl`. Maintenance used the shared module
staged at `/mnt/FR4G/Apps/muxmender/maintenance-cleanup-20260920` without changing
the deployed app. Automatic cleanup requires a future deployment.

Local verification: 519 tests passed, 3 skipped.
