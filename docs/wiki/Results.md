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


## Time and encoding details (next release)

Open a video's **Details** to see where its recorded processing time went:
encoding, picture quality checks, file checks, resource waits and pauses. These
bars show shares of recorded time, not completion percentages. Time waiting in
the queue before processing and unrecorded gaps are excluded. Older attempts
may have no breakdown; the app says when evidence is unavailable or cannot be
combined safely. **Refresh report** updates an open report without changing the
queue.

**Why this encoding was chosen** compares the tested options and explains why
an option won or was rejected. Sample encoding times exclude queue waits and
GPU-sharing pauses. The clip counts matter: a trial stopped after one clip
cannot be compared directly with a total for three clips. Sample size and speed
estimates do not guarantee the full-file result or approve a replacement.
Reports load when you open Details, so a large history does not add report-file
scans to normal dashboard refreshes.

## Warnings about original audio

Some source files already have audio decoding problems, such as CRC errors.
MuxMender can still reduce the video size when it can copy the compressed audio
unchanged and verify every copied packet and its timing. The result and any
replacement record keep the warning so you know the issue was already present.

This preserves the audio; it does not repair it. Unreadable tracks or changes
introduced by conversion still prevent approval.

## Warnings about the container

A result may say that extra bytes followed the declared
container. If those bytes caused read errors, the app can use an exact temporary
copy ending at the complete Matroska container boundary. It does not rewrite the
original, remove media tracks or rebuild playback timing.

The usual full validation is still required. The replacement record keeps the
warning, and normal cleanup removes the temporary read copy. Incomplete
containers or extra container segments need separate investigation.

## Read progress without guessing

A video usually goes through inspection, sample comparison, full encoding,
validation and, when selected, replacement. A percentage describes the current
stage. **100% on one stage isn't 100% of the whole job.** Time estimates also
refer to the current stage unless explicitly stated otherwise.

The app shows **Working…** when
a check cannot report a percentage, or **Waiting** when it has not started.
The card explains the current task and shows how long that check has been
running. A moving bar without a percentage shows activity, not estimated
completion.

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
