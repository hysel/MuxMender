# Keeping work files under control

The automatic workflow uses the request's saved size-aware or fixed savings
policy. Cleanup never changes that policy or the quality/preservation thresholds.
Existing queued requests retain their saved settings.

Generated files are now cleaned automatically after a rejected full conversion,
a no-conversion trial decision, or a processing exception with a retained source.
Successful replacement uses the existing published-file checksum verification
before cleanup. Successful safe copies and samples selected for review are kept.
Graceful cancellation now runs the same shared finalizer. Abrupt termination
without a terminal record remains protected pending recovery review.
See [post-task cleanup](post-task-cleanup.md) for the outcome-by-outcome policy.

Cleanup removes generated media and bulky raw frame/packet/quality evidence.
It preserves status, selection and trial summaries, replacement receipts, error
logs and a cleanup journal. Internal hardlinks can be removed only when all links
are inside the artifact manifest. Links shared outside that scope are retained.

The cleanup root must be separate from source media. Linked paths, missing
sources, changed files, unresolved publication/recovery records and active
states prevent cleanup. Cleanup failure is recorded without changing a successful
replacement into a failed conversion or hiding the original processing error.

Deletion is permanent at the filesystem level. ZFS snapshots can retain blocks;
logical bytes deleted are not the same as newly available pool space. Deployment
is required for the running app to use these changes; historical maintenance is
a separate, explicitly reviewed operation.
