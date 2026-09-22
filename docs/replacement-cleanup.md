# Cleanup after replacement

Once a replacement is confirmed, MuxMender can remove its temporary work files.
This avoids keeping a second collection of large test files after the library
has already been updated.

## What gets removed?

Eligible generated videos, temporary video/HDR data and large frame-check files
inside that completed job's own work folder. The published library file is never
a cleanup target.

Job history, quality summaries, validation and replacement records, and logs stay.
Safe-copy outputs, failed jobs and active tests are not cleaned automatically.

## What makes cleanup safe?

Before deleting anything, the cleanup service rechecks the published file against
its saved size and checksum. The validation and replacement records must agree,
and there must be no unresolved recovery marker. Linked files and paths that
could lead outside the job folder are excluded.

If cleanup fails, the successful replacement stays successful. The job reports
that cleanup needs attention; it does not start encoding the video again.

Deleted work files do not go to the recycle bin. Filesystem snapshots may retain
their data, so deleted bytes are not necessarily space immediately freed.

## Manual maintenance

The shared cleanup module supports a read-only preview. Deletion requires its
explicit execute option. When run outside the app container, receipt paths must
be mapped to the correct media root; never substitute a broad cleanup command.

Every deletion is recorded in the job's `artifact-cleanup.jsonl` journal.

## Recorded cleanup: 20 September 2026

Maintenance verified 19 completed replacements and removed 619 generated
artifacts: **65.694 GB** in total. Active work, source media, published files,
history and logs were retained. This was a maintenance run, not proof that the
running app has since been updated.

See the [status report](STATUS.md) for the merged code and deployment distinction.
