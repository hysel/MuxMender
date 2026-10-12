# Project status

## Current checkpoint: 12 October 2026

The clean-base public candidate completed runtime and generated NVIDIA image
checks. It does not inherit the private image's nonfree FFmpeg fallback or ship
another host's GPU qualification receipt. The shared conversion engine and
quality checks are unchanged.

Public Docker hosting is not available yet. A separate source-and-notice bundle
has been assembled for review, with recovered dependency notices and checksum
records. It has not been uploaded or marked approved for redistribution.
The isolated software/security scan completed against the exact tested candidate.
It reported 28 package findings: 21 medium and seven low, with no high or critical
findings reported. None listed a fixed package version. These are scanner results,
not a claim that every bundled native library is covered or that publication is
approved. Dependency findings still require review.
The corrected generated safe-copy lifecycle passed both conversion and container
recreation. The source stayed unchanged, and the validated output hash and history
were retained. The earlier receipt-filename failure remains in the append-only
log; the successful rerun has separate receipts. These are generated-file checks,
not real-library replacement, cancellation or public-installation certification.
Dependency review and anonymous-pull checks remain open.

The public recipe now keeps pip/wheel installation in a separate build stage.
The revised candidate passed runtime and generated NVIDIA image checks; its
security rescan remains pending. The isolated active-stage
cancellation test passed: observed native work stopped, the source was unchanged
and cancelled history survived recreation on the earlier candidate. Production
was not redeployed. See the
[security review](public-image-security-review.md) for findings and remaining work.

The installed app and library were not changed. The latest isolated GPU check
confirmed that the installed app was stopped; it was not restarted by the test.
Do not read this checkpoint as a live production queue report.

The README and user guide distinguish local/development packages from future
public image tags. Detailed test and dependency evidence stays out of the wiki.

## Historical checkpoint: 10 October 2026

Production remains on v59. The revised v60 package is building in isolation;
it enables checksum-pinned FFmpeg 9.0.2 by default while retaining the existing
qualified GPU validation reader. Deployment is not yet approved: image smoke
tests must finish successfully. The first staging attempt failed before Docker
on a Windows line-ending version guard; the revised package fixes that guard
and binds build progress to the archive checksum.

Generated paired FFmpeg 8/9 qualification passed all 82 modules on each runtime
with no skipped tests. Three historical track-count failures now have validated
full-source research copies, with reductions of 33.53%, 44.08% and 27.11%.
Only the first was tested in full on both runtimes; the others passed the current
baseline engine. These are potential savings, not reclaimed space: originals
remain unchanged. No material encoding speed or size gain from FFmpeg 9 has
been demonstrated in the paired full-source case.

Separate elementary-track diagnosis confirmed genuine AVC and AC3 decoding
failures on both runtimes. Their checks remain enforced. Video-reader failures
encountered during audio preflight now have an accurate explanation. Working
tracks were removed; compact evidence and validated test copies were retained.

## Historical checkpoint: 9 October 2026

The TrueNAS app is running v57. Its isolated image build and smoke tests passed,
including the packaged runtime, dashboard/API, NVIDIA encoding, GPU reader and
generated output presets. The active batch is still running; this is not a claim
that the whole library has finished.

The last checked batch had 12 verified replacements, three running jobs and 25
waiting jobs, with no failed or skipped jobs in that batch. All 12 replacements
recorded cleanup of redundant output media. Receipts and compact diagnostics
remain available. These counts are a dated observation, not live telemetry.

The empty-queue auto-start fix is tested locally and is awaiting the next image
qualification. New work starts an empty queue without a Resume click; manual
pauses with existing work and recovery/error pauses remain protected.

Scheduling tests on the installed v56 engine completed the same four excerpt
tasks in about 575/601/383 seconds with one/two/four workers. All twelve passed
technical and sampled quality checks. Available memory varied considerably, so
this does not establish a general 33.5% speed improvement. Dynamic admission
and the four-worker ceiling remain unchanged.

A separate intermediate AV1 setting passed one scene but failed the later
five-scene quality and aggregate size checks. No full conversion was started.
There is no new automatic quality exception for that setting.

Manually approved safe-copy replacements have durable receipts and count toward
lifetime savings, but their original result cards can still show the safe-copy
outcome. Reconciliation remains follow-up work.

## Historical checkpoint: 29 September 2026

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
