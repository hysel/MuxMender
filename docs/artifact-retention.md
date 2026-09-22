# Keeping work files under control

The automatic workflow defaults to a **25% minimum size reduction**. A result
exactly 25% smaller qualifies on size; anything below that is kept as the
original. Quality and preservation checks still have to pass. The app form,
API default and shared automatic CLI use the same default. Explicit settings
remain editable; the UI offers 25% (default), 20%, 15% and 10%. Lowering the size
target does not lower quality requirements. Existing queued requests retain
their saved settings.

Generated files are now cleaned automatically after a rejected full conversion,
a no-conversion trial decision, or a processing exception with a retained source.
Successful replacement uses the existing published-file checksum verification
before cleanup. Successful safe copies and samples selected for review are kept.
Cancellation/interruption is not automatically treated as disposable work.

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
