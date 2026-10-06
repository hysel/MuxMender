# Project status

## Current checkpoint: 29 September 2026

Production was last observed on v44. The working tree prepares
[v45](../deploy/truenas/RELEASE-20260929-v45.md): saved per-stage processing
limits, shared adaptive HDR-reader settings, smaller evidence files, clearer
retry labels and generic TV descriptions. Updating this repository does not
deploy the app or change existing queued jobs.

Targeted Linux regression: 208 passed, six skipped. Local UI/batch-review tests:
16 passed. The faster frame-threaded HDR reader remains research-only pending
qualification; there is no claimed full-job speed improvement. Quality and
preservation checks remain unchanged. See [processing limits](processing-timeouts.md).

## Historical checkpoint: 28 September 2026

The working tree and observed production execution identify v41. See
[supported use cases](SUPPORTED-USE-CASES.md) and the
[v41 release notes](../deploy/truenas/RELEASE-20260927-v41.md).
The latest inspected v41 batch had five replacements, five skips and eleven
failures. TrueHD decoding, AV1/MP4 timestamps, validation-resource waits and
DV/HDR10+ static metadata require follow-up. This is a recorded snapshot, not
live queue telemetry. Local changes are not a published commit or deployment.

## Historical checkpoint: 22 September 2026

The remainder records that earlier checkpoint. Its version, queue totals and
automatic-DV restrictions are not the current support policy.

Updated 22 September 2026. This is a repository and recorded-results update,
not a live reading of the TrueNAS queue.

The full-file research batches are now complete: 19 runs across 18 unique sources,
with 16 validated copies and two remaining keep decisions after reconciling a
successful retry. Potential reduction is **79.912 GB (65.863%)**; originals remain
untouched. See the [reviewed checkpoint](research-checkpoint-20260922.md) for
evidence, limitations and release preparation. These are not production replacements.

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

The full-file tests and result reconciliation are complete. Repeat the folder
audit, agree the deployment checkpoint and check recovery before
another long production run. The [roadmap](TODO.md) includes the remaining HDR,
hardware, speed and usability work.

The [research notes](animation-research-status-20260921.md) and
[experiment log](research-worklist-20260921.md) retain detailed evidence. Their
entries are historical snapshots; later entries may supersede earlier ones.
