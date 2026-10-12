# Project status

## Current checkpoint: 12 October 2026

Performance integration work is active, not released: SDR now has an explicit
shared GPU-reader dispatch path, but it requires a separate SDR scope. Existing
HDR qualification does not enable it. The public reader still has HEVC/AV1
decoder support only; H.264 needs a separately built and checked artifact.
An optional root-owned host receipt can be loaded from
`/opt/muxmender-host-qualification/qualification.json`, checked against the
image's exact reader hash, GPU, driver and visibility. This retains private
host evidence without putting it in a public image or trusting writable output.
The completed generated matrix now covers AV1 and HEVC, each at 8 and 10 bits,
with 67–77% less reader time. Decoder errors and dropped-frame detection are
reported separately. Generated fixtures alone do not grant a production scope.

The full-source AV1 8-bit SDR comparison has since passed: 136,818 exact frame
records, unchanged source hash, all damage controls rejected, and reader time
reduced from 27m 1s to 2m 55s (89.23%). A private bundle now combines this measured
Matroska SDR scope with the existing three HDR scopes.
The generated shared-workflow comparison also passed: encoding, full validation
and quality scoring took 65.63 seconds with CPU readers and about 58.46 seconds
with GPU readers, a 10.92% reduction at unchanged 94/90 quality thresholds. This
short-fixture timing excludes source generation and codec-discovery trials; it
is not a projected speedup for every library file. The isolated published-image
runtime check also passed with the updated shared code mounted read-only: the
real host-receipt loader selected GPU reads, all 1,464 frame records matched,
and unchanged quality checks passed. CPU and GPU workflows took 64.86 and 58.07
seconds respectively (10.47% less). The run removed 146,546,042 temporary bytes.
The private receipt is installed for the isolated check, not enabled in production.
The final image has now also passed qualification; no deployment occurred.

The v61 code-only candidate is built and qualified. It inherits the exact
published v60 digest, so runtime dependencies are unchanged. The runtime suite
passed 227 tests with nine skips. Generated GPU checks and final host-reader
checks passed without mounting development application code. The final shared
workflow was 10.59% faster, with identical quality scores and exact frame records.
The initial launcher used a disallowed localhost API address and received 403;
the corrected launcher resumed against the same image without rebuilding.
Image ID: `sha256:a2cd06a2d83e3a32ed0557edcb3b787cde832c4d8e0dc4e360df69ed848c255c`.
Publication to GHCR is still pending. Production remains unchanged.

Next-update UI change: GPU sharing saves directly from its toggle, without an
Apply button. Saving feedback, duplicate-submit protection, a bounded request,
failure rollback and server reconciliation are tested with mocked requests.
Older in-flight polls cannot undo an acknowledged setting change. The live
sharing status remains separate from the saved preference. Not deployed to v60;
the existing server-side yielding policy and media checks are unchanged.

The public preview image `ghcr.io/hysel/muxmender:20261010-v60` was uploaded by
browser-approved run 38268420839. Registry digest:
`sha256:89d4bf3fc38f2198ea4df7d576f00ce6841899022a13bdb21ace80fc3e6aa7d3`.
Anonymous download verification passed for the manifest and all 19 blobs
(239,514,350 bytes), including the exact qualified configuration image ID.
This was a complete registry-content download check, not a fresh Docker
installation or execution. Existing runtime/lifecycle qualification remains
applicable; production was not deployed or restarted. Cleanup still waits for
installation and rollback verification. The README and wiki now describe the
public preview; source, notice and build materials accompany the release.

## Earlier preparation on 12 October 2026

The browser-approved publication reached GitHub but stopped at downloading the
draft assets: the job had read-only repository permission. All four draft assets
remain present with verified hashes; no registry upload occurred. The publication
job now requests contents-write access behind the same browser approval, with
checkout credentials disabled and all image/material hash checks unchanged.
Four offline publication checks pass; the corrected live run remains pending.

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
security rescan completed with 22 findings (16 medium, six low). All six previous
pip/wheel findings were absent; remaining findings and custom-library coverage
still require review. The isolated active-stage
cancellation test passed: observed native work stopped, the source was unchanged
and cancelled history survived recreation on the earlier candidate. Production
was not redeployed. See the
[security review](public-image-security-review.md) for findings and remaining work.

Post-publication cleanup is being prepared from a read-only inventory. No files
have been deleted. The [cleanup plan](release-cleanup.md) protects source/license
materials, compact evidence, production history and rollback assets.

The consolidated batch passed all four revised-image lifecycle checks: safe-copy
conversion, active-stage cancellation and history retention after recreation for
both workflows. Source files stayed unchanged. The batch also collected installed
dependency sources/notices and a read-only Docker inventory for later cleanup.

The refreshed canonical source bundle covers 111 Ubuntu source versions and 332
Rust crates, with no notice-discovery gaps. One Ubuntu source version came from
the previously checksum-verified supplement; its descriptor signature remains
unverified. The bundle SHA-256 is
`da587f868087b0bba52b40257a9d56cd23641fbdc6cf97e24ae41a5cb3cffda7`.
Privacy and redistribution review, final release materials and public-pull checks
remain open. Passing these checks does not approve publication or cleanup.

The compact image-materials draft now contains 2,213 notice/recipe files with
verified hashes, source references and build pointers. The separate source
archive is not copied into the image. Three new offline packaging tests passed;
the preparation result is retained on the development dashboard. Final custom
component notice/license review remains open.

Upstream archive notices have since been added: the expanded draft contains
2,307 files (9,606,710 bytes). A notice-bearing candidate context is prepared
for a separate administrator-launched image build. It preserves the tested app
and media binaries and does not approve registry publication. The one-time
TrueNAS publication script passed four Linux static/mock-shell tests, including
dry-run and rejected image/research-placeholder cases; no real upload was run.

The notice-bearing candidate has now passed: 203 runtime tests, eight skipped,
and ten generated NVIDIA tests. Its image ID is
`sha256:20bceb9acd80f3bcf9e6a81312f4eede6d576b06fab978ab48e5da48f10c8c04`.
All 148 installed package versions and the three checked FFmpeg/reader hashes
match the preceding qualified runtime; Docker reused its executable layers.
The prior runtime scan remains relevant, not a new scan of this image digest.

The remaining six PyAV wheel system libraries matched the exact AlmaLinux RPM
code sections and recorded source RPM identities. Together with the previous
26 upstream matches, all 32 embedded library code sections now have matching
evidence. This is not whole-file reproducible-build or RPM-signature proof.

Reviewed source and notice assets are uploaded to a draft GitHub preview release
and staged on TrueNAS with matching checksums. Conditional public publication was
approved; the registry credential must be entered on the server. No image has
been pushed, no public download announced, and cleanup has not started.

Publication is switching to browser approval in GitHub Actions at the user's
request. A hosted-runner workflow is prepared to load and publish the exact
tested image with automatic credentials, without rebuilding or GPU access.
The export script is staged for an administrator command on TrueNAS. Three
targeted workflow/export tests and ten monitor tests passed; live export and
authenticated publication are still pending.

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
