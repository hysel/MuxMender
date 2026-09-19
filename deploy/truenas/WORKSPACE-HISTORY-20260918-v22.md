# Workspace history and recovery — v22

## Included

- Latest attempt per video with expandable prior attempts; published container
  changes are grouped. Active retries are identified, not presented as old failures.
- Completion-based sorting, natural filename sorting, confirmed-savings sorting,
  queued/started/finished timestamps and operation labels.
- Clear finished results, Undo clear and Show archived. These are view operations;
  they do not erase the processing ledger, validation evidence or media.
- Folder/batch filters, new batch IDs, persisted view preferences and release IDs.
  Older records retain their original values; unknown dates/versions stay unknown.
- All durable request history remains available; the UI renders 20 videos at a time.
- Distinct efficient, unsupported, quality-check, processing-error, ready-copy and
  replacement outcomes. New jobs retain compact candidate/quality evidence.
- VMAF scores are not described as a percentage of visual quality preserved.
- Separate sample savings estimates, retained-copy reduction and confirmed library
  reduction. Existing publication receipts and lifetime savings remain intact.
- Stage-specific encoding/validation/publication labels, heartbeat age, waiting and
  resource-throttling reasons, overall request counts and selected-batch counts.
- Latest linked worker progress is selected, including Windows path normalization.
- Both API channels must be healthy for Connected; bounded request timeouts and
  last full refresh timestamp make stale/disconnected state visible.
- Keyed Results rendering preserves details and focus. Reordering is deferred while
  a result contains keyboard focus. Dark mode, labels, contrast and mobile checks.
- Retry uses a new source-fingerprint/history preview and a fresh confirmation.
  Replacement retries still require explicit approval; active or successful work
  cannot be repeated through Retry. Publication recovery blocks it.
- Recovery inspection lists journals. Source-side publication backups/staging and
  manual receipts block retry/cleanup. Recovery involving originals stays manual.
- Explicit two-step cleanup for failed/interrupted request-generated media only:
  preview exact paths/sizes, confirm deletion, recheck containment, file signatures,
  single-link files, symlinks/junctions and current request state. Never recursive
  deletion; originals, source recovery files, reports and history are retained.
- Includes v21 reject-only efficiency screening and baseline-floor fixes. No new
  quality-threshold relaxation, CPU fallback or automatic replacement policy change.

## Persistence and upgrade

Keep the existing `/output` host dataset mounted at the same container path.
`/output/ui-requests/requests.json` holds requests, batches, preferences and archive
IDs. Migration is additive (`schema_version: 2`); old records/unknown fields are
preserved. Keep the existing dataset snapshot/backup policy and old image for
rollback. Do not clear the output folder to refresh Results.

The staging/build process does not pause/resume work or change media. Before
deploying, let currently running jobs drain; restarting interrupts active workers.
The existing app settings, GPU assignment, UID/GID, mounts, port and environment
should remain unchanged. No new environment variable is required.

Build on TrueNAS:

```sh
sudo docker build -f /mnt/FR4G/Apps/muxmender/app-build-20260918-v22/deploy/truenas/Dockerfile.app -t muxmender-app:20260918-v22 /mnt/FR4G/Apps/muxmender/app-build-20260918-v22
```

Set the existing app image tag to `20260918-v22`, repository `muxmender-app`.
This is a staged source release: the Docker build and deployment require a user
with Docker access. Staging alone does not change the running container.

After deployment, check footer/API version, active/pending counts, old history,
and resource profile. Try Clear finished results, Undo, Show archived and filters.
No media deletion is part of that check. The queue is never resumed automatically.

## Verification

Local regression result: 392 tests run, 3 skipped, no failures. Desktop dark-mode
and 390-pixel mobile browser checks found no horizontal overflow. Expanded details,
keyboard focus and scroll were retained through a refresh. This is not a formal
Section 508 certification or a full screen-reader audit.

Run `python -B -m unittest discover -s tests` with `PYTHONPATH=python;tests;.` on
Windows (colon-separated on Linux). Automated coverage includes archive/undo,
additive migration, replacement retry confirmation, active/successful deduplication,
orphan recovery markers, stale cleanup previews, linked-file refusal and UI focus,
attempt grouping, timestamps, sorting, evidence and accessibility checks.
Browser review uses a read-only proxy; no production control POSTs or media changes.
