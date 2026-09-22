# Read-only investigation findings

No production code, validation limits, running queue or source media changed.
Diagnostic script: `tools/investigate_timing_evidence.py`.
Copies of retained generated evidence are under
`E:/MuxMender-TestOutputs/failure-diagnosis-20260920`.

## Timing case A: actual preroll established

Failing extraction uses input seek `-ss 477.72`, output `-t 10`, stream copy,
all tracks, and `-avoid_negative_ts make_zero`.

Source keyframes around the seek: 466.591, 467.967, 478.395, 485.777 seconds.
All 476 reference video packet hashes match the bounded source probe, in its
selected interval. First selected packet PTS is 467.967 and last is 487.862.
Every matching PTS shifts by exactly -467.884 seconds into the reference.
This establishes keyframe preroll (9.753 seconds before requested seek), not
duplicated or time-stretched packet content. Sample format duration is 20.019s.

Root issue: requested sampling duration does not describe actual stream-copy
window when seeking inside a long GOP. The prior doubled-duration guard then
rejects the resulting sample. Widening that guard does not correct sampling.

Next experiment: explicitly select a verified source keyframe near the requested
scene and derive the sample end from that chosen start. Confirm exact selected
frame identity, decodeability, audio/subtitle boundaries and equal reference/
candidate intervals. Reproduce with long-GOP generated fixtures first. Do not
silently use non-keyframe copy or re-encode the quality ground-truth reference.

## Timing case C: timestamp change isolated to HDR finalization

Compared all 1,080 audio packets across reference, retained encoded
`hevc_nvenc-balanced-cq25-p7-0-before-hdr-finalization.mkv`, and final sample.

- Reference -> encoded pre-finalization: all payloads/order/counts identical;
  all 1,080 audio PTS values exactly match.
- Pre-finalization -> final: all payloads/order/counts identical; PTS differences
  are 716 at 0 ms, 1 at +1 ms, 300 at -1 ms, 62 at -2 ms, 1 at -3 ms.
- Finalizer extracts source video timestamps and supplies them explicitly to
  mkvmerge for injected raw HEVC, but supplies copied audio/subtitles from the
  reference without explicit per-track timestamp files.

This isolates the change to the finalization pipeline, not the GPU encoder.
The most likely mechanism is mkvmerge's audio timestamp reconstruction; an
isolated remux experiment is still required to prove the exact mechanism and
the correction. Do not characterize the 3 ms difference as harmless by assumption.

Next experiment: compare default remux to remux with explicit extracted audio
timestamps (correct MKV track IDs, not assumed ffprobe indices). Check every
packet PTS/DTS/duration/hash, audio-video alignment, metadata, chapter mapping
and decode. Then test other audio formats and full sample quality. No acceptance
tolerance increase is part of this experiment.

Reference: https://mkvtoolnix.download/doc/mkvmerge.html (--timestamps)

Both issues remain open until a corrected path passes controlled reproduction
and real sample validation. No replacement or deployment approval inferred.

## Controlled experiments, 21:33–21:35 local

Script: `tools/experiment_timing_preservation.py`; retained reports under
`E:/MuxMender-TestOutputs/failure-diagnosis-20260920/experiment-20260920-213425`.

Timing case C combined raw-HEVC + copied-track remux reproduced the exact 3 ms
failure pattern locally using MKVToolNix 102.0. Adding `--disable-lacing`
preserved all 1,080 audio PTS/DTS/durations/payloads exactly. All five subtitle
track packet counts/payloads/timestamps matched too (two empty tracks). Entire
sample video/audio decode passed. Output overhead increased by 5,011 bytes.
By contrast, explicit audio timestamp import introduced a 5 ms discrepancy and
duration changes; reject that attempted correction. Generic single-input remux
did not reproduce the failure: the combined-finalizer layout matters.
This supports container audio lacing as the mechanism, not GPU encoding.
Still required: integrate narrowly, regression coverage across audio codecs,
full HDR preservation validation and real scene quality tests on target build.

Timing case A: seeking directly to keyframe PTS 478.395 still includes earlier preroll.
Adding output-side zero trim at that seek discarded the desired keyframe and
left audio before video; reject that approach. Source keyframe DTS is 478.311.
Seeking one millisecond before DTS (478.310), then output zero trim, produced
240 matching source video packets over 10.093 seconds, starting at the desired
478.395 PTS. A/V decode passed. Video starts at 0.084s, audio at 0.025s; verify
their source-relative offsets and boundary packet semantics before acceptance.
This is a diagnostic candidate, NOT a hardcoded fix or an approved algorithm.
Need deterministic timebase-derived selection, packet alignment verification,
long-GOP/fractional-rate fixtures and equivalent reference/candidate coverage.

## Follow-up qualification

The shared HDR finalizer now supplies `--disable-lacing` through
`preservation_mux_command`. The real Timing case C sample passed full structural
validation: 279 static HDR frames, exact HDR metadata, exact video timestamps,
exact geometry/color, and verified copied tracks. No timing tolerance changed.
This is not yet target-container or scene-quality qualification.

Generated AAC, EAC3 and TrueHD fixtures passed the diagnostic packet comparison
and decode checks. AC3 exposed a final packet duration change from 16 to 32 ms,
despite identical payload, PTS and DTS. A control remux with default lacing
produced the same discrepancy: this is a separate existing remux edge case,
not evidence of a no-lacing regression. Keep strict validation; investigate
boundary duration/discard-padding preservation before claiming broad support.
Evidence: `audio-fixtures-20260920-214232/report.json` in the diagnostic root.

Timing case A's 478.310 diagnostic sample has one unique contiguous source match for
each stream: 240 video packets and 312 audio packets. Both streams have the
same exact PTS shift of -478.311 seconds; available DTS shifts also match.
All reported packet durations are unchanged. Thus the observed 59 ms between
first audio/video PTS preserves the selected source alignment, rather than
introducing drift. The diagnostic timestamp is still not a production rule.

Local regression suite: 539 tests, 3 skipped, passed. No source replacements,
queue changes, Docker release or deployment performed.

## Dolby Vision matrix completed

TrueNAS run `run-20260921-011659-ace4b126` completed all three trials in
approximately 26 minutes 32 seconds. CQ22/CQ24/CQ26 passed structural checks
and common-render quality screening, but video size increased respectively
43.405%, 43.401% and 29.420%. None qualified for replacement. Screening scores
are not native Dolby Vision perceptual measurements. CQ26's different size
also means nearly identical CQ22/24 sizes alone do not establish ignored CQ
settings. No additional encode launched or source changed.

## General sampling fixtures and AC3 container evidence

Added `reference_sampling.py` with a source-timebase-derived keyframe planner
and strict unique contiguous payload/timestamp checks. It is deliberately NOT
called by automatic conversion yet. No source-specific timestamp is hardcoded.
The packaging manifest includes the module; this does not qualify the route.

`tools/qualify_reference_sampling.py` generates small H.264/PCM noise fixtures
at 24, 24000/1001 and 30000/1001 fps, each with zero and three B-frames.
All three zero-B-frame samples preserve identical packets and one common A/V
timestamp shift. All three B-frame samples decode, but fail the new strict
check because initial DTS availability changes. Do not ignore that discrepancy
without decoded-frame/timeline evidence. Repetitive sine packets were replaced
with seeded noise to make payload identity unambiguous. Evidence:
`sampling-fixtures-20260920-215141/report.json` under the diagnostic root.

MKVToolNix `mkvinfo -v` confirms the generated AC3 source's last audio block is
a BlockGroup with explicit BlockDuration 16 ms at container timestamp 1.984s.
The remux represents it as a SimpleBlock without that duration; ffprobe then
reports 32 ms. This localizes the discrepancy to lost container duration
information, rather than changed audio payload or start timestamp. A duration
preservation fix is still required; no acceptance tolerance was widened.

## Implemented solutions and final local qualification, 22:24 local

### Timing case A: complete-GOP, source-proven recovery

The shared auto workflow now invokes bounded keyframe recovery only when the
original reference fails its existing duration bound. Recovery selects a
source-timebase-derived start and a complete-GOP end, then independently proves
contiguous original packet identity, exact decoded pixels/display order, exact
display timing, and a common A/V timestamp shift. Initial missing DTS values
are admitted only within the source-reported reorder depth, only at the start,
and only with matching decoded-picture and timeline evidence. Interior missing
DTS, drift, changed pictures, missing frames and changed packet durations fail.
This is a sample-boundary correction, not relaxed output validation.

The actual Timing case A scene recovered to 13.263 seconds under the unchanged 20-second
bound. Evidence: `Timing case A-shared-recovery-221743/reference-keyframe-recovery.json`.
All six 24/23.976/29.97 fps, B-frame/no-B-frame generated tests pass through the
actual shared recovery. Subtitle events and a +1.5-second source timestamp
offset also pass. Mid-GOP truncation was found to omit a display frame; complete
GOP endpoints resolve this rather than ignoring the loss.

### Timing case C and AC3: preserve original copied-track block durations

The HDR finalizer keeps no-lacing packaging and now uses a final stream-copy
step: restored video from the packaged file, non-video tracks directly from
the source, with explicit source tags, dispositions and chapters. This retains
the source's AC3 final BlockDuration rather than accepting the reconstructed
duration. Existing strict copied-track checks remain unchanged. The extra
packaged intermediate is registered for owned-artifact cleanup; space checks
account for the extra copy.

AAC, AC3, EAC3 and TrueHD generated fixtures pass the actual shared strict
packet comparator and decode tests. All available audio timestamps/durations
match exactly (including TrueHD's prior 1 ms remux rounding).
Evidence: `audio-fixtures-20260920-222140/report.json`.

Real Timing case C sample: 279 HDR frames; exact static HDR, geometry/color and
frame timestamps; copied tracks verified. Common-render quality self-check
98.3066 mean / 97.4775 p5; candidate 94.2002 mean / 92.6542 p5, passing the
90/90 screening baseline. Output is 8.6659% smaller for this sample, not a
full-file savings claim. Evidence: `Timing case C-source-tracks-finalizer/`
`hdr10plus-preserve-11809645e3e9/`. These are HDR10 common-render VMAF scores,
not percent picture fidelity and not native Dolby Vision metrics.

Regression suite: 550 tests, 3 skipped, no failures. No image published, queue
resumed, Git operation performed or source replaced. TrueNAS Docker socket
access is denied to the SSH account. A code-only standalone qualification
bundle is staged at `/output/timing-qualification-20260920-r1/`; it needs an
admin Docker exec to qualify the deployed toolchain. The archive SHA256 is
`a7fef0234daebc7c4564c9d220c2bbfebef7d3828c2dcf89b28da203e6bec980`.

## TrueNAS qualification completed successfully

User launched the isolated package in the existing container. Run
`run-20260921-022542-441b594a/qualification.json` reports `passed: true`.
Timing case A's recovery retains exact decoded pictures and common A/V alignment in
13.263 seconds under the unchanged 20-second bound. Timing case C passes all 279
HDR frame, geometry/color, timestamp and copied-track checks. Candidate quality
screening is 94.1949 mean / 92.6667 p5; self-check is 98.3070 / 97.4777.
The sample is 8.6660% smaller. No full-file savings or new GPU encode is claimed:
the test used the retained encoded sample and exercised the corrected finalizer.
All inputs are unchanged, replacement is unauthorized and the queue is unchanged.

During monitoring, the prefix-quality helper was found to retain its previous
phase label and omit its known frame count. Local code now names both quality
passes and supplies `expected_frames` to shared progress reporting. This was
unit tested, not hotpatched into the running test. Final local regression suite:
551 tests, 3 skipped, no failures. The app image/release remains unchanged.
