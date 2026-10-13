# Automatic recovery after an update

Status: graceful-shutdown retry implemented in development, not available in the installed release. The earlier proposal
for a Prepare for upgrade button was withdrawn. There is no new preparation
button or API action in the development code.

The intended experience is to use Update in TrueNAS without preparing the queue.
When the new app starts, it should recover unfinished work automatically while
keeping the user's queue settings. A deliberate cancellation must stay cancelled.

The first implementation records active requests before stopping worker processes.
After restart, it checks source identity, cancellation and replacement records.
Eligible work is queued again automatically with the same settings and a new
request ID. The previous attempt and its evidence remain in history. A deliberate
manual queue pause is preserved. Completed jobs are not repeated.

This version **restarts the interrupted workflow**, not just the interrupted
stage. It does not reuse unverified partial files. It passed a Linux service
stop/start test with a sleeping worker and generated source bytes; that is not
yet a real container-upgrade or media checkpoint qualification.

Still needed for the complete upgrade-anytime experience:

1. Add durable processing checkpoints beyond the saved shutdown intent.
2. Bind checkpoints to the source content, request settings and compatible runtime.
3. Retain completed outputs separately from incomplete native-process files.
4. Resume from the last verified stage, repeating any stage whose proof is missing
   or incompatible with the new runtime. Never treat a partial encode as finished.
5. Reconcile replacement journals before starting more work, without publishing
   twice or deleting an unverified original.
6. Test graceful shutdown, forced termination, cancellation, changed inputs and
   runtime upgrades using generated fixtures, then an isolated container upgrade.

An interrupted encode may need to start again. Exact-frame continuation requires
a separate segmented-encoding design and additional timing and quality checks.
An abrupt kill before shutdown intent is saved, changed source, or ambiguous
publication still needs review. No replacement journal is automatically discarded.
Until the new path is packaged and upgrade-tested, let active jobs finish before updating.
