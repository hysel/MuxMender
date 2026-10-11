# Testing a new FFmpeg version

We keep a [fix ledger](fix-ledger.md) so a library upgrade does not leave us
carrying unnecessary workarounds—or accidentally remove a fix we still need.
The ledger records implementation families, regression tests, evidence and
unresolved cases. The package also inventories every current Python regression
module and test method, including tests not yet linked to a ledger entry.

This is a backfill from the current code and release records. “Implemented” does
not mean qualified on every file, GPU or FFmpeg version. Historical investigation
notes may describe withdrawn experiments; those are explicitly marked withdrawn.

## What the comparison tells us

The suite runs the old and proposed runtimes against the same generated fixtures.
Raw commands do not use MuxMender's recovery code. The managed chapter test then
checks our shared worker handoff and verified mapping. Both runtimes also run the
ledger-linked application regressions. Results record executable hashes, complete
version/configuration output, fixture hashes, skipped tests and failures.

The initial raw sentinels cover native MP4 chapters and AAC startup trimming.
Simple chapter fixtures may already pass raw FFmpeg or use a custom descriptor
that our managed route correctly refuses to discard. Those results do not
reproduce the private chapter failure and do not qualify removal of its handling.
Other ledger entries remain **coverage gaps** until their own raw reproducer is
added. The private aspect-ratio case and full-file GPU checks are still run by
the separate qualification tool. A mock-based regression is useful, but it is
not proof that FFmpeg fixed a media-processing issue.

The report can say:

- **Issue persists:** raw FFmpeg still fails; retain our handling.
- **Upstream fix candidate:** the old runtime reproduces the failure, the new
  runtime passes without our workaround, and linked regressions pass without skips.
- **Coverage gap:** a reproducer is missing, unavailable, skipped, or the baseline
  did not reproduce. Do not infer a fix.
- **Application or protection:** this is our queue/UI behavior, performance policy
  or a safety check. A library upgrade does not make it obsolete.

Nothing removes code automatically. Before retiring a workaround, repeat the
representative full-file test, verify negative controls still reject damaged or
changed output, and confirm all quality, timing, metadata and publication checks
remain intact. AAC fixture PCM equality alone is not full presentation-timing
proof. A library fix never removes the quality or savings requirements.

## Build the reusable package

```powershell
python -B tools/build_ffmpeg_test_package.py --destination E:/MuxMender-TestOutputs/ffmpeg-compatibility-tests-r1
```

The archive contains shared code, tests, tools, the ledger and a regression index.
It contains no media, FFmpeg binaries, credentials or production queue state.
Build a fresh snapshot for each planned upgrade. Verify the archive checksum
and `package-manifest.json` before execution.

## Run it on an isolated Linux worker

Keep source mounts read-only. Use executable pairs from the intended builds,
not an unqualified moving “latest” tag. Verify downloaded runtimes separately.
Never execute this suite or Linux reader payloads on the Windows workstation.

```bash
python3 -B tools/ffmpeg_compatibility_suite.py \
  --baseline-ffmpeg "$(command -v ffmpeg)" \
  --baseline-ffprobe "$(command -v ffprobe)" \
  --candidate-ffmpeg /opt/ffmpeg-next/bin/ffmpeg \
  --candidate-ffprobe /opt/ffmpeg-next/bin/ffprobe \
  --output /work/ffmpeg-comparison-001
```

The output directory must be new. `--command-timeout` controls individual test
budgets; the default is 120 seconds. `--skip-regressions` is diagnostic-only and
cannot produce a workaround-removal recommendation. Missing tests do not count
as passes. Temporary fixture videos are removed even on failure; receipts and
logs remain. Register a development-dashboard observer before a remote run.

For release qualification, also run the complete image smoke suite, real-source
HEVC/AV1 checks on the assigned NVIDIA GPU, selected quality presets, HDR/Dolby
Vision preservation, copied audio/subtitles/attachments, cleanup and restart
recovery. Rebuild and independently requalify the patched GPU reader whenever
its source version changes. The generated sentinels do not replace those tests.

## Current upgrade finding

The pinned 9.0-branch comparison build passed three chapter remux checks, but its
NVENC SDK 13.1 requirement exceeds the installed driver's API 13.0 support. That
is a build/driver incompatibility, not proof that stable FFmpeg 9.0.2 requires a
driver upgrade. The signed-source 9.0.2 diagnostic build with SDK 13.0 headers
successfully encoded short HEVC/AV1 clips on the existing driver, but both still
reproduced the undeclared-to-square aspect-ratio mismatch. Three full chapter
remuxes passed with our verified mapping enabled. This does not establish that
raw upstream behavior no longer needs that mapping.

The baseline harness self-check reproduced changed AAC PCM after raw MP4-to-MKV
copy and correctly made no removal recommendations. The simple chapter fixture
did not reproduce the private duplicate-track issue. Full runtime comparison,
quality metrics and custom-reader qualification remain separate work.
Production remains on the existing pinned runtime.

The isolated 8.0.1 baseline run executed 80 ledger-linked test modules (644
tests). Its first run had two failing modules: adaptive-search mocks omitted
the frame count required by the quality evidence contract, and the old research
container lacked the pinned PyAV dependency. The corrected fixture passed all
11 adaptive tests; with PyAV 18.1.0 in an isolated test directory, all 10 copied
audio recovery tests passed, including generated DTS and TrueHD preservation.
The original report and separate rerun logs are retained. Eleven skipped tests
remain coverage gaps, not passes. These results do not qualify FFmpeg 9 or
justify removing a compatibility workaround.

The subsequent paired comparison completed all 80 modules on both runtimes
(644 tests each). The baseline had no failing modules. Both runs skipped ten
tests. The minimal 9.0.2 build failed three modules because generated fixtures
require absent libaom/libx264 encoders; its quality-metric stack is also missing.
This is incomplete build coverage, not a qualified replacement runtime.

The raw AAC fixture had matching source/output PCM on 9.0.2 and mismatching PCM
on 8.0.1. Source PCM itself differed between versions, so the observation still
needs packet, presentation-timing and representative full-file investigation
before removing AAC handling. The raw chapter fixture on 9.0.2 failed the strict
time-base comparison (1/1000 to 1/64000). No workaround was removed. Generated
temporary media was cleaned up; reports, binary hashes, capability inventories
and logs were retained on the isolated worker.

The follow-up workflow-feature build is isolated from production. It adds
libx264/libx265/libaom, VMAF 3.0.0, zscale, subtitle and libplacebo filters, and
rebuilds the CUDA reader against the same signed FFmpeg 9.0.2 source. NVENC
headers remain at 13.0 to match the current driver. Sources and the PyAV wheel
are checksum-pinned; installed build-package versions are recorded in the image.
This is workflow-feature coverage, not an identical replica of every optional
library in the baseline image.

Its generated checks include the paired ledger suites, VMAF self-scoring and
damaged-picture controls, and complete short HEVC/AV1 CPU/GPU frame records for
SDR and PQ. Geometry, frame-loss and timestamp differences are rejected. The
test container has no media mount and cannot publish or install a reader.
Representative long-file, malformed-bitstream, HDR10+/Dolby Vision and shared
reader-dispatch qualification are still needed before production migration.

The first workflow-feature run built successfully and executed all 644 tests
per runtime without skips. Both runtimes failed the same three modules. The
VMAF model failure was traced to missing `xxd`: upstream's model-embedding build
step silently omits built-in models when that tool is absent. The recipe now
requires it and runs a default-model self-test during image construction. A UI
message-order bug was fixed and its report DOM checks pass locally. Neither fix
is a media-validation waiver.

Short generated AV1 SDR/PQ reader checks passed, including geometry/frame-loss
negative controls. Follow-up diagnostics traced the HEVC fixture failure to its
small height: the driver rejected the coded height of 128 against a minimum of
144. With a 320x180 fixture, all 24 CPU/GPU frame records matched exactly for
both SDR and PQ. The qualification fixture now uses that supported size; this
does not change production geometry checks or certify unsupported dimensions.

The exported-runtime diagnostics reproduced the DTS terminal-packet difference:
FFmpeg 9 reports 5 ms in the source and 10 ms after audio recovery. Both retain
the same 256-sample discard padding and decode to identical 192,000-byte PCM
streams with equal hashes. The old-runtime pair reports 10 ms in both files and
decodes to equal 192,512-byte streams. This establishes a timing-report mismatch,
not permission to waive it. The timing-preservation failure remains unresolved.
Stage-by-stage records locate the change in the PyAV audio relay itself, before
the final MKVToolNix merge: PyAV reads a 5 ms source packet but its remuxed file
reports 10 ms. Packet payloads, discard padding and decoded samples remain
equal. Further work must preserve the explicit duration in the relay, rather
than loosening the final comparison.

A constrained shared recovery repair now restores the source's terminal duration
with a stream-copy `setts` duration expression and a decoded-source frame-size
hint. It requires matching complete packet inventories, hashes, presentation and
decode clocks, flags and padding. Only one short padded terminal duration may
be repaired; the source is never modified. Matching durations do not activate
the repair or add another validation gate. The regular full validation is still
required afterward.

On generated two-second video/audio fixtures, both the baseline and candidate
passed the unchanged full preservation validator for all 48 video frames. The
candidate's source and repaired output both report the original 5 ms terminal
packet and retain identical decoded-audio hashes. This is short generated
preservation evidence, not VMAF, long-file or production approval. A generated
two-audio-track test also passed the unchanged complete preservation validator.
It exposed a literal language-spelling change during MKVToolNix remux; the copy
repair now restores the original language tag rather than widening comparison.
The corrected image rerun passed on October 10: all 82 ledger modules passed
on both runtimes with no skipped tests. VMAF self/damaged controls and all four
SDR/HDR HEVC/AV1 reader comparisons passed, including frame-loss and geometry
negative controls. A launch with a missing isolated
PyAV subprocess path was retained as a failed attempt; corrected reruns succeeded.

These diagnostics used an isolated copy of the host's `libnuma.so.1` solely to
load the exported runtime; its hash is recorded in the report. They are not an
image qualification. Their generated temporary media was removed and frame,
packet and hash records retained. No candidate runtime or reader is approved
for installation until representative full-source qualification is evaluated.

## Paired full-source follow-up

The next isolated package reuses the qualified image and the shared automatic
engine. It evaluates four private history cases on both runtimes, serially:
track-count failure, video-decode failure, audio-decode failure and an
already-efficient keep. Each case retains its existing quality, resolution and
savings settings. Sources and production history are mounted read-only; no
publication or production runtime change is possible. An administrator launch
is required. A completed evaluation is not proof of a validated output: the
report distinguishes validated copies, retained originals and errors. This
sample establishes case evidence, not a library-wide conversion-rate estimate.

The four-case paired run completed on October 10. The historical track-count
case passed full validation on both runtimes, saving 33.53% with unchanged
balanced quality requirements (mean 94, fifth percentile 90). Both evaluations
took about 1,079 seconds; this case shows no material runtime speed or size
improvement from the upgrade. The source-video reference-frame diagnostic and
source-AC3 exponent error remained on both runtimes. The already-efficient case
was retained by both: tested candidates missed savings or measured quality.
All eight evaluations recorded unchanged source identity and successful working
artifact cleanup. Two validated research copies remain; no originals were
replaced and no library space was reclaimed. The video diagnostic surfaced
during an audio-only preflight input probe; that context is not evidence of
damaged audio and must not be reported as such. Decoder integrity checks remain
required before approving conversion.

### Source-reader follow-up

The shared engine now attributes an explicit video-decoder tag to the source
video reader, even when the diagnostic arises while opening an audio-only
preflight. It retains the failure and raw evidence; no decoder diagnostic is
suppressed. The UI explains that the video reader failed before conversion.
All 11 source-preflight tests passed on each Linux runtime, including truncated
audio rejection and timestamp-clock regression checks (22 tests, no skips).

Read-only elementary-track diagnosis is running separately. The first case's
complete extracted AC3 track passes strict decoding on both runtimes and yields
the same decoded PCM hash. Its container-time AVC diagnostic is therefore not
evidence of corrupt audio. The completed eight-track diagnostic run confirms
actual AVC reference/macroblock errors and corrupt decoded frames in that case
on both runtimes. The second case's extracted AC3 also fails on both runtimes
with exponent/block decoding errors and corrupt decoded frames. These are not
container-only warnings and cannot be approved by changing an error label.
The second case's raw video diagnostic emitted null-muxer timestamp errors;
it does not establish video corruption or source timeline failure, because
elementary extraction discards the container timestamps. No repair or
conversion approval is inferred from these diagnostics.
Temporary extracted tracks are deleted after their paired diagnostic runs;
logs and checksums are retained. The exported diagnostic runtime is not used
to claim new image qualification or deployment approval.

The next controlled diagnostic scanned all 157,327 AC3 packets with independent
decoder contexts and identified 33 undecodable packets. It produces no repaired
audio and does not permit dropping or concealing those packets. A 60-second
NVIDIA AVC feasibility read completed but retained the same input-probe
reference-frame diagnostic; zero process exit status alone is not strict
acceptance. The next two historical chapter/track-count cases are being tested
serially through the shared full-source baseline workflow. No candidate-runtime
or hardware repair qualification is inferred from that follow-up.
