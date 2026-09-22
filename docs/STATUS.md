# Project status

Updated 21 September 2026. This is a repository and recorded-results update,
not a live reading of the TrueNAS queue.

## Where we are

The development checkpoint is merged into `main` (`65d8d32`). It brings together
the shared processing engine, validation fixes and dashboard controls. The code
still identifies itself as v34; merging it did not build or deploy a Docker image.

The clean checkout completed **636 tests: 633 passed and 3 were skipped**.
The development checkout produced the same result. Hardware qualification is
tracked separately; unit tests cannot prove that every card or file will work.

## Last recorded library snapshot

The read-only inventory accounted for all 82 supported files. There were no
unreadable paths and no files missing from processing history.

| Outcome at that checkpoint | Files |
| --- | ---: |
| Converted, with the current file matching its replacement record | 51 |
| Queued | 14 |
| Kept because the tested result was not worthwhile | 9 |
| Kept because the workflow could not handle the case yet | 4 |
| Failed, without a later successful replacement | 3 |
| Changed since the recorded result; needs investigation | 1 |

These counts do not mean the queue has finished. Production was paused at this
research checkpoint. Its live state was not rechecked for this documentation update.

## What the research tells us

Several previously failing cases now have successful full-file test copies,
including timing, MP4 and artwork-related cases. Other candidates remain too
large or fall below the selected quality target. Keeping those originals is
the correct outcome for the tested settings.

A combined Dolby Vision/HDR10+ test passed full-file preservation and three-scene
quality checks. That research copy was about **86.9% smaller (7.34 GB less)**.
This is potential savings from one test, not newly reclaimed library space.
The automatic app route remains disabled until integration is qualified.

Ordinary Dolby Vision preservation passed on a full copy, but broader sample
tests rejected the tested quality/size settings. It is not ready for automatic
conversion. A damaged-audio example needed a separately approved repair; silent
source repair is not part of the normal workflow.

Performance work reduces repeated validation and history lookup overhead.
The recorded stage benchmarks are promising, but do not establish a single
whole-library speedup. GPU validation is not globally enabled.

## What happens next

Finish the remaining full-file tests, reconcile results and repeat the folder
audit. Then prepare an agreed deployment checkpoint and check recovery before
another long production run. The [roadmap](TODO.md) includes the remaining HDR,
hardware, speed and usability work.

The [research notes](animation-research-status-20260921.md) and
[experiment log](research-worklist-20260921.md) retain detailed evidence. Their
entries are historical snapshots; later entries may supersede earlier ones.
