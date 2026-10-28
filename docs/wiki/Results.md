# Understand results and disk savings

Results tells you what happened to each video and why. The latest attempt is
shown first; details keep earlier attempts available.

| Outcome | What it means |
| --- | --- |
| Inspection complete | The app read the file. It didn't convert it. |
| Copy ready | A full converted copy passed the applicable checks. The original remains. |
| Replaced | The checked output is in the library and the original was removed. |
| Original kept | No acceptable smaller output was found, or you chose to keep it. Read the reason. |
| Needs attention | An error prevented completion. Open details before retrying. |
| Cancelled | You stopped this attempt or removed it from the queue. Cancellation itself isn't a processing error. |
| Interrupted | Processing stopped unexpectedly. Check details and any recovery files before retrying. |

A kept original isn't necessarily an error. It may already be small, or the
tested alternatives may miss the quality or savings target. Repeating the same
request won't necessarily change that.

The results filter applies to the list, not the queue. Selecting completed
results doesn't mean active processing has stopped. Check Overview for that.
Search, sort, folder filters and report exports help you review a larger batch.
Hiding old results doesn't delete videos or erase processing history.
Cancelled attempts appear in completed results, separately from errors. Older
failed attempts remain in history until a later retry produces a new result.

## Read progress without guessing

A video usually goes through inspection, sample comparison, full encoding,
validation and, when selected, replacement. A percentage describes the current
stage. **100% on one stage isn't 100% of the whole job.** Time estimates also
refer to the current stage unless explicitly stated otherwise.

An overdue update means progress information is old. A connection warning means
the browser couldn't obtain fresh information. Neither proves the worker stopped
or the job finished.

## What counts as space saved?

File-size reduction compares the original and output. **Lifetime library space
saved** counts confirmed replacements, not samples or retained copies.

If you keep both versions, they use more space together. Storage snapshots can
also retain deleted data, so the pool's free space may not immediately match the
app's recorded savings. Sizes shown as GB use decimal units.

## What happens to work files?

The app removes eligible temporary artifacts after verified replacement and
keeps compact history and receipts. Safe-copy outputs stay available for you.
Interrupted work and unresolved recovery files may need attention rather than
automatic deletion. Don't manually sweep an active job's folder.
