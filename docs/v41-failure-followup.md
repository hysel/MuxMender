# V41 follow-up: 28 September 2026

Development only. Production queue and original media remain unchanged.

## Validation admission

Three inspected jobs failed while waiting for the shared heavy-reader lock.
The decorator passed the execution timeout into admission. The patch separates
them: ordinary admission remains cancellable and reports elapsed wait, while
the wrapped reader retains its original execution deadline after admission.
The memory-protecting single-reader lock remains. Explicit bounded admission
is still available to callers/tests. Six Linux tests passed, including contention,
cancellation, release after process death, symlink rejection and timeout separation.
This does not implement fair ordering or qualify whole-run throughput. A hung
holder remains subject to its execution timeout; operational monitoring is needed.

## Other failures

- AV1/MP4: two jobs repeated equal-DTS mux errors across six AV1 settings each.
  Reordering/container-clock reproduction is pending. No timestamp rewriting,
  dropped frames or blanket source rejection has been introduced.
- TrueHD: five jobs failed strict source preflight. Decoder compatibility versus
  damaged input remains unresolved. Tracks are not automatically removed.
- Combined DV/HDR10+: static metadata counts differ. The diagnostic now names
  both source and output record types. Cleaned intermediates require a fresh
  bounded reproduction before selecting a preservation repair.

The updated DV preservation unit suite passed all 17 tests on Linux, including
missing and added metadata diagnostics. This verifies diagnostics and existing
unit behavior, not a successful conversion of the failed source.

Quality and savings requirements are unchanged. No release, commit, push or
production retry is part of this patch.

## Bounded reproduction findings

An isolated NVIDIA test reproduced the equal-DTS AV1/MP4 failure. Disabling
encoder reordering also failed. The copied reference has duplicate/backward
decoded timestamps near its tail; a bounded source-reader probe also showed
tail anomalies. Existing source-verified keyframe recovery failed its framehash
check. This does not prove the entire original has a broken playback timeline;
bounded decoder flushing and cut boundaries need further isolation. No timestamp
rewrite or frame dropping is proposed as a substitute for that evidence.

The exact AV1 equal-DTS mux failure is now classified for same-encoder trial
deduplication. Other encoders remain eligible and the outcome stays incomplete,
not a no-savings decision. Three targeted Linux tests passed. This avoids repeated
CQ/preset trials but does not repair the failed reference or approve conversion.

The combined DV/HDR10+ excerpt reproduced with the improved diagnostic. The
initial static HDR comparison passed; a later comparison found no source static
records but both mastering-display and content-light records on the output.
Thus the old missing-metadata message obscured an added/repeated-record case.
Decoder/bitstream signaling needs verification before changing acceptance.

The initial TrueHD diagnostic reported exit code zero and reached beyond 90
minutes, but incorrectly omitted stderr for successful exit codes. The follow-up
below corrects that diagnostic interpretation; neither result clears the source.

Private diagnostic artifacts are tracked on the development dashboard. Source
paths and identifying media titles are deliberately excluded from this document.

## HDR decoder fix qualified on the failing excerpt

The reference produced intermittent absent static side data with two default
decoder threads. Reading the identical file with one thread, or two slice
threads, produced static metadata on every one of the first 240 pictures.
The shared metadata-reader options now request slice threading for HDR/DV frame
evidence. This preserves a single frame context while allowing slice work; it
does not synthesize metadata, carry values across frames, or relax comparisons.

FFmpeg's [HEVC reader implementation](https://raw.githubusercontent.com/FFmpeg/FFmpeg/n8.0.1/libavcodec/hevc/hevcdec.c)
tracks static SEI persistence as decoder state. The exact upstream cause of the
observed frame-thread discrepancy has not been established; the workaround is
supported by the same-file comparison, not a blanket claim about all builds.

The formerly failing combined DV/HDR10+ ten-second sample subsequently passed
all 240 frames of structural preservation and final decode checks with the
patched reader. All 54 targeted Linux regressions passed. This is a recovered
sample, not a full-file quality/savings qualification or permission to publish.
SDR AV1 timestamp-tail errors did not improve with slice threading; those remain
a separate investigation. Full-file reader performance still needs measurement.

Another 69 Linux regression tests passed with test temporary files placed on the
research work volume (the container's small temporary filesystem correctly
triggered disk-reserve checks on the initial attempt).

## TrueHD warning confirmed despite successful process exit

The full 3-hour diagnostic reached EOF with exit code zero but emitted
`quant_step_size larger than huff_lsbs`. Single-threaded and slice-threaded
15-second retries reproduced the same warning. Production's strict log check
is correct; the earlier exit-code-only diagnostic was not sufficient. The source
size and modification time still matched the failed job. Decoder compatibility
versus bitstream damage remains unresolved; no automatic audio removal or error
suppression is authorized.

## Shared multi-scene result

All five ten-second scenes passed the patched shared automatic DV/HDR10+ route:
1,200 pictures total, with preservation and unchanged quality floors satisfied.
The lowest scene mean was 95.99 and lowest fifth percentile 94.32 in the common
HDR rendering domain. CQ24 was selected with an estimated 17.62% sample saving.
This is not native DV perceptual certification, actual full-file savings or
reclaimed library space. Full-output validation is still required.

A separate PyAV 18.1.0 reader using libavcodec 62.28.102 also reported the TrueHD
warning on the short source prefix. Switching to that newer library alone does
not clear the source. It also did not provide a monotonic AV1 reference clock.

## Full-copy qualification and AV1 cut-boundary evidence

A full shared-engine HDR safe-copy qualification is now tracked on the
development dashboard. It repeats scene checks before encoding and validating
the complete output. Production remains paused; no source replacement or
deployment is part of this experiment. Full-file savings are not yet known.

That first attempt subsequently stopped before full encoding: the older full
service independently tested a different 30-second scene and measured a 10.58%
video-payload increase. This vetoed the shared five-scene selection despite its
17.62% aggregate estimate. No complete output was created in that attempt.

The automatic handoff now revalidates the shared selection, source content,
encoder settings and requested quality floors instead of repeating a separate
single-scene eligibility policy. Standalone callers retain the existing bounded
preflight. Full-file size and preservation checks are unchanged. All 48 targeted
workflow, full-service and selection regressions passed on Linux. A fresh
isolated full-copy qualification is running; this change is not deployed.

Extending the AV1 reference by three, eight and sixteen nominal frame durations
did not pass decoded-source identity checks. Comparing the captured frame hashes
for the first extension narrowed the failure further: sample pictures through
index 296 matched a contiguous original slice, but picture 297 matched original
index 740 instead of the expected 738 and repeated the preceding sample
timestamp. The longer original decode retained those intervening pictures with
ordered timestamps. This is evidence against treating this cut as a faithful
reference, not proof that the complete source is damaged.

The next recovery experiment should evaluate a bounded interior scene while
retaining enough decoder context beyond it, and prove its pictures and timing
against the original. It must not fix a cut by silently dropping pictures,
rewriting their timestamps, or weakening the quality floor. That recovery is
not implemented or qualified yet; duplicate-failure deduplication alone is not
an AV1 conversion fix.

The development observer now keeps the outer research job as the authority for
completion while showing the currently running nested worker's stage and
progress. Older attempts and completed fixtures cannot take over that display;
either a stale parent or stale selected worker keeps the observation stale.
All twelve Linux observer regressions passed. The live full-copy observer was
restarted with this fix; the remote media job was not restarted.

## Full-file mux memory failure

The next full-copy attempt passed shared selection, encoded the complete video
and injected its dynamic metadata, then failed at final muxing. The ordered mux
used `max_interleave_delta=0`, which allows indefinite buffering while waiting
for sparse tracks. The source's forced-subtitle track had only five packets,
ending at 237.28 seconds of a roughly 7,447-second video. A second subtitle
track had a gap of about 550 seconds. The 1 GiB memory guard stopped the mux.
See [FFmpeg's interleaving documentation](https://www.ffmpeg.org/ffmpeg-formats.html).

The first development experiment used finite ten-second interleaving while retaining
the same byte-memory guard and all startup, seek, timing and payload checks.
The byte guard also applies to finite explicit interleaving commands: a time
bound alone is not a memory ceiling. The workflow now propagates the full
service's specific error instead of replacing it with a generic missing-report
message. Fifty-one targeted Linux regressions passed before live qualification.

The remux-only experiment completed muxing in approximately 26 seconds at a
measured peak of 35.5 MiB. Every video, audio and subtitle packet payload and
clock matched, and startup passed. However, five later seek points failed:
the bounded read returned video without accompanying audio. The original passed
the inspected seek point. The finite-buffer production-code change was therefore
withdrawn; the memory guard and improved failure reporting remain.

The separate mkvmerge experiment passed with the same 1 GiB memory ceiling,
packet identity and seek requirements. It muxed in 17.45 seconds at 108.6 MiB
peak. All 178,540 video packets, 232,707 audio packets and both subtitle tracks
matched their original payloads and clocks. Startup and all six seek checks
passed; stream inventory, chapters and dynamic-HDR header also matched.

The shared full DV service now prefers this identified-track Matroska path when
mkvmerge is available. It maps actual identified track IDs, carries source video
labels and default/forced flags, disables lacing and keeps the same memory guard.
Mux percentages update the existing progress channel. All 71 targeted Linux
regressions passed. A new full-copy qualification is starting; remux success does
not prove the converted output will pass all checks. No deployment or source
replacement is authorized by these experiments.
