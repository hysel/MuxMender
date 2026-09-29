# Remaining conversion blockers

Development work only; no deployment or original-media changes.

## Short sources

The shared ordinary workflow now uses one complete, byte-identical reference for
sources under six seconds instead of attempting three tiny GOP excerpts. The
selector requires matching full-source SHA256 and byte-size evidence before
accepting one reference. Quality, stream, timing and final savings checks remain.
A generated three-second SDR video with audio passed full HEVC conversion and
validation (61.50% synthetic size reduction). All 743 remote regression tests
passed at that checkpoint. Subsequent subsecond and Dolby Vision evidence follows below.

## Rotation

A generated MP4 with a verified 90-degree display matrix was encoded to HEVC MKV
with automatic pixel rotation disabled. The output retained the exact matrix
and original 320x192 dimensions. Shared admission now accepts complete display
matrices and compares all nine coefficients in the output; encoding and quality
comparison disable automatic pixel rotation. The remote suite passes 747 tests.
A three-second generated rotated MP4 with ALAC audio passed full conversion,
quality and preservation checks (46.99% synthetic reduction). Missing output
audio packet durations are accepted only after compressed packet identity and
timing checks plus independent decoded PCM, duration and presentation checks.
All 36 decoded audio frames matched, with zero timestamp difference.
The AAC follow-up below now also passes generated 90/180/270-degree cases at
0.5, 3 and 45 seconds. This does not qualify changing per-frame transforms,
arbitrary projection/shear, or all HDR combinations. An earlier probe whose fixture lacked a rotation matrix
is not qualification evidence.

## Still open

### AAC priming and container choice

The generated AAC failure was reproduced with diagnostic artifacts retained.
The Matroska copy declared CodecDelay but the installed decoder emitted one extra
1,024-sample priming block (142 frames versus 141 source frames). A separate-copy
MP4 experiment retained the source audio packets and matched all 141 decoded
frames with identical PCM and zero timestamp difference. This is evidence for a
source-compatible container fallback, not permission to ignore extra decoded
samples. The shared workflow now chooses MP4 when source preflight finds explicit
MP4 AAC priming, and keeps the same container through intermediate steps to avoid
millisecond timestamp rounding. A generated three-second rotated MP4 passed full
encoding, quality, audio and frame validation, producing a 50.05% smaller copy.
Container-aware naming and journaled replacement now support validated MP4
outputs with explicit container evidence. A disposable generated source completed
the full conversion-to-replacement path; the published MP4 hash matched the
validated output. Remote tests cover extension changes, same-path publication,
case-insensitive conflicts, late destination races and interrupted replacement
with the original and backup retained. All 754 regression tests pass. No actual
library original was replaced. Longer-source sampling and additional stream
combinations still need coverage beyond the cases below.

The generated 45-second 180-degree AAC MP4 now passes the complete shared
workflow (51.56% synthetic reduction). Recovery references preserve source
rational packet and frame clocks, use a common exact MP4 movie clock and one
integral-second offset. This avoids per-track rounding without increasing the
timestamp tolerance. A half-second 270-degree case also passed (40.44% synthetic
reduction). That checkpoint passed 755 remote tests.

### Short Dolby Vision sources

The shared automatic route now uses one byte-identical whole-source reference
for short DV clips, with matching source hash, size and complete decoded-frame
coverage. It measures the full reference and candidate container sizes for this
case rather than mixing elementary-video and container byte counts. Full-file
preflight no longer asks a short source for an impossible 30-second sample.
Generated NVIDIA Profile 8.1 tests passed the automatic selection, full encoding,
quality, timing, audio and RPU checks: two seconds (24 frames), half a second
(six frames), and a 24-frame variable-timing clip. Synthetic reductions were
66.07%, 64.94% and 65.02%; these are not library savings estimates. The suite
passed 758 tests before the separate monitor identity regression was added.
The read-only research monitor also now distinguishes separate jobs on one
server, so one completed test cannot overwrite another job's dashboard status.

Other side data and unusual tracks, unresolved metadata/timing, interlaced
quality/savings fallback, and genuine Dolby Vision Profile 5/7 and other-vendor
paths remain part of the active effort. They have not been declared completed or
removed from scope.

### Timed data tracks

A generated MOV timecode track could not be muxed into MP4 by the installed
FFmpeg, but MOV retained its packet payload, timestamps, codec tag, extradata
and timecode metadata. The complete shared HEVC workflow then passed all quality
and preservation checks, producing a 52.49% smaller generated MOV. Data tracks
are now included in copied-packet verification rather than rejected by type;
MOV-family sources with data tracks retain MOV. Journaled publication requires
explicit matching container evidence. Other data codecs still need actual
runtime and preservation evidence; unsupported muxing never authorizes dropping
the track.

### Other stream side data

Non-HDR side data is no longer rejected merely for being unfamiliar. Candidates
must retain it exactly, with display matrices checked separately and encoder CPB
properties excluded because they describe the new bitstream. HDR metadata stays
on its dedicated full-frame validation path; Dolby Vision cannot enter the SDR
route. A generated side-by-side stereo-layout source passed the complete shared
HEVC workflow with native dimensions, layout metadata and quality preserved
(64.85% synthetic reduction). Unknown types that fail preservation still retain
the original; this is not a claim that every encoder can preserve every type.

Latest full remote regression run: 762 tests passed, with no skips. These changes
remain local development work; no app deployment or original-media replacement.

### Interlaced H.264 quality and field order

The generated fallback test exposed a real field-order bug: translating a
container `tb` label into an explicit bottom-field override changed a source that
actually decoded top-field-first. The shared encoder now retains decoded frame
flags instead of overriding field dominance from that label. Full decoded field
order and timing checks remain mandatory. FFmpeg's [frame flag definition](https://www.ffmpeg.org/doxygen/trunk/group__lavu__frame__flags.html)
describes the presentation flag used by decoded interlaced frames.

The research rerun passed generated top- and bottom-field-first MPEG-2 sources:
60 frames each, 720x480 at 30000/1001, without scaling or deinterlacing. H.264
NVENC copies saved 42.96% and 43.07%. Both woven-frame and separated-field VMAF
passed: conservative mean scores 97.99/97.98 and fifth-percentile scores
97.58/97.54. The shared SDR quality evaluator now requires both checks for
interlaced input, with exactly two quality fields per validated frame. These
objective checks are not a visual certification of arbitrary interlaced content.

The shared automatic workflow now supports H.264 hardware candidates, adaptive
quality search and the dashboard format option. It only considers H.264 when
explicitly included in playback-verified formats; existing HEVC/AV1-only choices
are unchanged. For the app, include `h264` in `MUXMENDER_PLAYBACK_CODECS` after
confirming client playback. The CLI accepts it in `--playback-verified-codecs`.
Both generated field orders passed complete automatic selection, full encoding
and validation with HEVC, AV1 and H.264 allowed. The tested HEVC/AV1 initialization
failures remain specific runtime evidence, not a ban on every GPU. Real-client
playback and other-vendor interlaced qualification are not claimed by these tests.

The complete remote regression suite passes 765 tests after this change.

After automatic H.264 selection, app/CLI option parity and adaptive-search
integration, all 768 remote regression tests pass. Existing unverified-codec
rejection is covered explicitly; adding an option does not enable it for old
HEVC/AV1-only app configurations.

### Profile 7 source evidence and generated MEL fixture

A read-only bounded inspection of all 21 Profile 7 declarations found five
samples containing RPU metadata and two containing enhancement-layer NALs.
The five parsed RPU samples comprised one MEL case and four FEL cases. Zero
sample counts are not whole-file absence proof, and no source was relabeled or
converted by this inspection. The earlier empty-declaration recovery remains
dependent on a fresh complete-file scan.

A generated 24-frame two-layer MEL fixture is now available for preservation
tests: the tool independently reports Profile 7 MEL, with 24 RPU NALs and 52
enhancement-layer wrapper NALs. This establishes a test input, not a working
conversion route. Next is re-encoding the base layer while verifying retained
enhancement content, all RPU metadata and decoded frame timing/quality.

The upstream [dovi_tool documentation](https://github.com/quietvoid/dovi_tool)
provides separate demux/mux operations and distinguishes MEL-compatible metadata
conversion from Profile 8 conversion that can remove FEL mapping. The research
will not treat these operations as interchangeable or silently discard FEL data.
Genuine Profile 5 rendering-preserving encoding and FEL reconstruction remain
unfinished; neither is enabled for replacement.

### Generated MEL layer-preservation result

The 24-frame generated MEL test now retains Profile 7 container signaling,
byte-identical enhancement video, complete ordered RPU semantics, geometry and
frame timing after NVIDIA HEVC base-layer encoding. The resulting test copy is
72.10% smaller. Common HDR10-render quality scores are 99.73 mean and 99.19 fifth
percentile; these are not native Dolby Vision perceptual qualification.

This test caught two important distinctions. Raw RPU serialization can change
without changing its parsed contents, so enhancement video bytes and ordered RPU
semantics are verified separately. Also, the existing raw-HEVC FFmpeg mux helper
signaled Profile 8 even with retained enhancement data. The successful research
test uses mkvmerge and explicitly compares the full Profile 7 configuration.

Reusable layer-evidence validation now checks every RPU, complete frame coverage,
exact enhancement payload and container configuration with bounded-memory reads.
Its result is deliberately not publication approval. FFmpeg still logs an
enhancement-configuration mapping warning on the generated mkvmerge containers;
that interoperability issue, full-file track/timing tests and client playback
remain pending. No production Profile 7 route is enabled by this checkpoint.

All 775 remote regression tests pass, including missing/changed enhancement
payloads, Profile 8 relabeling, incomplete or reordered RPU coverage, cancellation
and package parity. The RPU reader also bounds trailing-data reads instead of
loading an arbitrarily large remainder into memory.

The [current upstream FFmpeg Matroska reader](https://ffmpeg.org/doxygen/trunk/matroskadec_8c_source.html)
has an explicit `hvcE` parser; the research runtime reports that mapping as
unknown. An isolated newer-reader comparison is the next diagnostic step, not
a reason to delete the enhancement configuration or suppress all decoder errors.

### Profile 7 reader compatibility and full-track fixture

An isolated Linux FFmpeg build (`N-126782-gdc52424419-20260923`) reads both generated
MEL files without the mapping diagnostic seen in the research runtime's 8.0.1.
All 24 decoded base frames per file match across the two readers. The downloaded
archive's SHA-256 matched its published release digest. No installed executable
or production image was replaced. This identifies a reader limitation in the
tested old runtime, not corrupt enhancement payload or a reason to discard it.

A second generated fixture adds variable presentation times, a three-second
start offset, AC-3 audio, subtitles, chapters and an attachment. Repackaging the
previously encoded picture sequence retained exact copied audio/subtitle packets,
attachment content, chapters, Profile 7 configuration, enhancement video and
ordered RPU metadata. Both files passed clean full video/audio decoding with the
isolated reader. The complete output is 56.08% smaller. This extends mux/validation
evidence; it is not a new variable-rate encoder or real-client playback test.

The shared timestamped-video mux helper now has a preservation-aware enhancement
option. It uses the tested mkvmerge path without the single-layer relabel filter,
supports explicit variable timestamps and refuses existing destinations. Callers
must still prove layers, configuration and full timing independently. Automatic
Profile 7 candidate selection and full end-to-end route integration remain open;
the helper alone does not authorize conversion or replacement.

### Shared full-layer extraction

Complete Profile 7 extraction now uses the same guarded, cancellable, logged
Workflow service as ordinary conversion. It selects the actual primary stream,
uses a new owned evidence directory, inventories every RPU and hashes the entire
enhancement video with bounded memory. It reports MEL/FEL evidence separately
from conversion eligibility; an FEL inventory is not permission to re-encode its
base layer without reconstruction validation.

The generated variable-timing fixture passed this shared extraction path and the
existing complete decoded-frame audit: 24 frames, unchanged geometry, static HDR,
timestamps, enhancement payload and RPU contents. The original fixture hashes
were checked throughout. Automatic selection/full conversion integration remains
unfinished; the next step is using the ordinary HDR encoder/finalizer on the
extracted base layer before recombination and the full preservation audit.

The DV timing validator now uses exact rational timestamps and rejects missing,
nonfinite or nonincreasing presentation evidence. A floating-point NaN could
previously evade a difference comparison. Negative starts and genuine variable
intervals remain supported; no fixed frame-rate or resolution list was added.

### Shared HDR base-layer encoding and duration-header recovery

The generated MEL fixture now passes encoding through the ordinary HDR encoder
and finalizer, followed by enhancement-layer recombination and full frame, RPU,
enhancement, audio, subtitle, chapter and attachment verification. The output is
54.44% smaller; common-render quality is 99.86 mean and 100 fifth percentile.
This is generated end-to-end encoder evidence, not automatic candidate-selection
integration or real-player certification.

The test exposed another false rejection: mkvmerge reported the 1.970-second
elapsed video length, while FFmpeg reported the 4.970-second endpoint for the
same three-second-offset timeline. All 24 packet presentation times/durations
matched. The shared metadata validator now handles this specific representation
case only after complete per-stream packet counts and extents match, and both
headers match the measured span or endpoint. Full decoded-frame and copied-packet
checks remain mandatory. Actual changed packet endpoints, missing evidence,
unresolved packet durations and unrelated header differences still fail.

The new proof reads packet evidence with bounded memory and cancellation checks.
It is shared by ordinary full validation and HDR finalization; no tolerance was
widened and no original or production file was modified. The remote regression
suite passes 782 tests after this change.

### Reusable MEL candidate service and secondary tracks

The new shared MEL candidate service now performs guarded extraction, ordinary
HDR base encoding, enhancement recombination, source-track restoration, full
frame/layer/packet validation and quality screening. Copied-track validation was
extracted from the ordinary Workflow method and reused, including its existing
AAC presentation checks. No frontend-specific encoding or acceptance policy was
added. Automatic reference selection and queue integration are still pending.

A generated source with secondary AVC video, audio, subtitles, an attachment,
chapters, variable picture intervals and a nonzero start passed the complete
service. Its 24 primary frames, complete RPU contents, enhancement payload and
copied streams were retained. The output is 53.89% smaller; common HDR10-render
quality is 99.86 mean and 100 fifth percentile. This remains research-copy
evidence with publication authorization explicitly false, not native Dolby Vision
perceptual or real-client certification. All 784 remote tests pass.

Two integration failures were resolved without relaxing preservation checks:

- The isolated newer FFmpeg reader build requires NVENC API 13.1 for encoding;
  the host exposes 13.0. The service can explicitly use the already-working
  encoder executable while retaining the capable demuxer. Both executable paths
  are recorded; no driver, GPU, codec or CPU fallback is silently selected.
- Timestamp import initially shortened the last picture from 83 to 80 ms.
  Supplying the source's final picture endpoint as an extra timestamp boundary
  preserves that hold and the complete packet extent. The boundary does not add
  a picture. This is shared with HDR finalization; source resolution, picture
  times and timing tolerances are unchanged. Average-FPS metadata is not used to
  reject a full independently verified variable presentation timeline.

### MEL reference selection and complete-file refinement

The MEL service now uses the existing source-verified keyframe sampler and the
ordinary measured candidate selector. A longer generated source produced three
distinct GOP windows; each passed exact compressed-packet and decoded-picture
identity checks and retained all enhancement metadata. Short sources use the
whole unchanged original as their single reference. An unverified playback codec
is never encoded, and a runtime error stays attached to its candidate rather than
becoming a GPU-family ban or a cached successful skip.

Two settings were compared against the same three scenes. CQ24 passed with
80.19% aggregate sample savings; CQ28 failed quality. Full-file testing then
caught two cases that short samples did not establish:

- Different base-layer GOP structure shifted 20 scene-refresh markers around
  boundaries. Reinjection of the original display-ordered RPU sequence after
  enhancement recombination fixed this. Every RPU and the unchanged enhancement
  payload were independently checked over all 288 generated frames; scene-refresh
  differences are not normalized away.
- The complete CQ24 copy failed the unchanged fifth-percentile quality floor
  (86.01). A higher-quality CQ20 generated copy passed at 97.82 mean / 95.18 fifth
  percentile, while reducing total size by 81.89%. This is synthetic evidence,
  not a projection for library content or native Dolby Vision visual certification.

Sample selection and the candidate service are shared code. The complete-file
refinement was a controlled research call; automatic retry orchestration and
frontend/queue integration remain unfinished. No replacement is authorized by
these reports, and no production image or source media changed.

### Bounded full-file refinement

The shared MEL service now retries a measured full-file quality rejection using
the existing adaptive candidate policy. It keeps source-specific rate limits,
the selected savings policy and unchanged quality floors. Attempt limits are
explicit; structural errors are reported separately and are not cached as an
already-optimized source. No publication is authorized by this service.

The generated 288-frame test automatically rejected CQ24 and passed CQ20 on its
second and final permitted attempt: mean 97.82, fifth percentile 95.18, and
81.89% smaller. Complete timing, RPU ordering, enhancement payload and copied
tracks passed independent checks. These are synthetic test results, not a
library savings prediction. Frontend integration and native Profile 5/FEL
qualification remain unfinished.

### Shared automatic layered adapter

Profile 7 now dispatches from the common Dolby Vision workflow into the layered
service instead of failing the Profile 8.1-only requirement. Complete source
RPU inventory distinguishes MEL from FEL before candidate encoding. Compiled
HEVC backends for the selected hardware are evaluated against actual source
references; a vendor name alone is not an exclusion.

A generated end-to-end adapter run passed inspection, scene comparison,
automatic full-file refinement and independent preservation checks. The result
remains a separate copy with explicit `publication_authorized=false` and
`integration_qualification_required=true`; this is not native Dolby Vision
visual qualification. All 793 regression tests passed remotely. No production
image or queue changed. Native Profile 5/FEL reconstruction and physical
qualification on other vendors remain open.

### Profile 5 native-render evidence

A generated 24-frame Profile 5 input was re-encoded using NVIDIA HEVC, retaining
all ordered RPU records, configuration, geometry and decoded timing. The copy
was 67.3% smaller. A common libplacebo render of both DV inputs scored 99.89 mean
and 100 fifth percentile. Disabling DV processing on the candidate (negative
control) scored 0.21 mean and 0 fifth percentile. This establishes that the
comparison detects this rendering failure, not merely the presence of DV tags.
Synthetic code values are not real-title or Dolby-certified visual validation.

The comparison is now a shared packaged service, tested remotely on the same
generated files; all 796 regression tests passed. It preserves geometry, disables
automatic rotation, does not override frame rate and does not authorize
publication. Profile 5 full encoding orchestration, unusual-track/timing cases
and long-file resource handling remain open. In particular, intermediate
lossless render copies must be replaced by streaming comparison before this
path is suitable for long library files.

Current upstream [libplacebo renderer interfaces](https://github.com/haasn/libplacebo/blob/master/src/include/libplacebo/renderer.h)
include an enhancement-frame input for FEL composition. The inspected
[FFmpeg libplacebo filter](https://github.com/FFmpeg/FFmpeg/blob/master/libavfilter/vf_libplacebo.c)
does not connect that interface. Therefore installing a build with libplacebo
alone is not evidence of functioning FEL composition. The shared single-layer
comparison explicitly does not accept that case; a renderer integration is
still needed, not a blanket assertion that the GPU cannot support it.

### Streaming Profile 5 comparison and shared candidate service

The native-render comparison now streams both libplacebo outputs directly into
the common HDR metric. It writes no intermediate render video and does not trim
to a sampled prefix. The generated comparison reproduced the earlier scores
exactly, with complete expected frame coverage.

A shared single-layer candidate service now reuses ordinary encoder settings,
timestamp reconstruction, copied-track checks and complete decoded-frame
comparison. It independently extracts and compares the source and final ordered
RPU sequence, preserves Profile 5 signaling, and uses the native-render metric.
The generated 24-frame test passed at 70.93% smaller, 99.89 mean and 100 fifth
percentile. All 798 regression tests passed remotely, including package parity.
No source changed and publication remains explicitly unauthorized.

Variable timing, additional tracks, automatic candidate orchestration and
physical playback qualification remain open for this new service. The generated
fixture is not proof of equivalent results for all Profile 5 media.

### Profile 5 timing/tracks and automatic selection

A generated Profile 5 fixture with variable presentation timestamps, nonzero
start, secondary AVC video, AC-3 audio, subtitles, chapters and an attachment
passed the shared candidate service. All copied tracks, ordered RPU and complete
frame timing were preserved. The separate copy was 46.50% smaller with the same
99.89 mean / 100 fifth-percentile native-render scores.

Profile 5 now uses the same reference-selection, measured-decision and bounded
full-retry controller as the layered route. Its evidence must use the native DV
render domain; interpreting its base as ordinary HDR is not eligible. The
generated multi-track fixture also passed this full automatic adapter. All 799
regression tests passed. Publication remains false, not inferred from a green
test or retained DV tags.

The test selected the RTX 5050 Vulkan driver through a process-only ICD setting.
Automatic renderer discovery, longer multi-reference Profile 5 testing and FEL
composition remain open. A default container software renderer must not be
mistaken for hardware qualification or silently impose CPU-scale runtimes.

### Hardware renderer discovery and open-GOP sampling finding

Native quality evaluation now probes the visible Vulkan renderer. The default
TrueNAS environment selected software rendering; discovery rejected that as
hardware evidence, then successfully used the already-installed NVIDIA EGL
library through a child-process-only ICD manifest. The RTX 5050 quality result
matched the earlier explicit-driver run. No driver installation, host-file edit
or global environment change was needed. All 802 regression tests passed.

A normal-CLI 24-second generated Profile 5 test exposed an open-GOP boundary
issue: the first scene had 24 displayed frames and 24 RPU records, but two later
cuts had 22 displayed frames and 24 RPU records. Source packet/picture identity
checks passed for the displayed slice; that does not prove correspondence for
the extra non-displayed metadata records. The candidate service rejected those
scenes and the original stayed unchanged. Boundary-aware reference recovery is
the next required fix; dropping RPU entries without an alignment proof is not
an acceptable shortcut.

### Open-GOP reference recovery verified

DV reference preparation now checks displayed-frame/RPU coverage before any
candidate encoding. A mismatched cut triggers a nearby source-verified boundary
retry; no RPU records are removed. If bounded retries cannot produce a usable
cut, selection evaluates the complete original source instead of treating its
format as ineligible. Source packet/picture identity checks remain unchanged.

The normal CLI test, using the installed research FFmpeg and automatic hardware
renderer discovery, rejected two ambiguous starts and produced three distinct
24-frame/24-RPU references. Full 288-frame conversion and validation then passed,
with a 78.47% smaller generated copy. Publication was explicitly false and the
source stayed unchanged. All 804 regression tests passed. This proves the
observed sampling recovery, not every possible pre-cut damaged DV bitstream.

### MEL native-DV and HDR10 fallback views

MEL quality evaluation now renders its native Dolby Vision view as well as its
HDR10 fallback. Full verified layer evidence is required to enter the MEL
renderer; FEL, incomplete coverage and missing enhancement/RPU hashes are not
treated as MEL. Selection sees the weaker mean/fifth-percentile scores, and
both views must pass, alongside independent EL/RPU/track/frame preservation.

The generated 288-frame test passed: native DV mean 98.91 / fifth percentile
96.92; HDR10 fallback 97.82 / 95.18. The separate copy remained 81.89% smaller.
All 805 regression tests passed remotely. No publication authority was granted.

FEL composition still needs renderer integration. A fresh environment check
confirmed the isolated research account is unprivileged and has no compiler,
build system, development headers or Docker executable. Approval was requested
to prepare a separate disposable build environment; production app, queue,
host drivers and original media would stay untouched. This is an unfinished
software/toolchain path, not evidence that the NVIDIA card cannot process FEL.

### Shared Profile 8 routing and bounded sample refinement

Explicit AMD/Intel Profile 8 requests now enter the shared source-driven
candidate service instead of a vendor exclusion. The established NVIDIA/auto
Profile 8.1 route is unchanged; physical AMD/Intel qualification remains open.
The common Profile 8 candidate checks both native DV and compatible fallback
views and uses the weaker scores, alongside full RPU/track/frame preservation.

Generated NVIDIA comparison runs reached encoding and validation. CQ20 retained
quality but increased size; CQ24/28 missed the quality floor. The engine correctly
kept the original. The research harness had expected a converted copy and failed
that assertion; this is not evidence of a media-processing crash or permission
to lower the quality requirements.

The shared DV selector now also uses the ordinary adaptive search for bounded
sample-quality retries, preserving rate caps and reference identities. At most
four additional candidates are tried by default. Structural/runtime failures do
not trigger quality retries. All 809 regression tests passed remotely, including
retry-budget, unchanged-reference, rate-cap and structural-failure coverage.
An end-to-end generated run of the new retry path remains to be verified.

### Sample refinement verified and automatic non-NVIDIA routing

The generated Profile 8 end-to-end retry run passed. Initial CQ24/28 candidates
missed the quality floor. Bounded refinement tried CQ20 and CQ18 (quality passed,
but outputs grew), then found CQ22: 8.02% smaller, combined mean 96.12 and fifth
percentile 92.15. Native DV and fallback views, complete frame/RPU/track checks,
and the full candidate validation passed. The source remained unchanged and
publication stayed false. This small generated test used a zero-percent savings
threshold to exercise search; production savings requirements are unchanged.

Automatic hardware selection now chooses the same shared evaluator when existing
discovery identifies AMD/Intel without NVIDIA. Explicit NVIDIA, mixed-vendor and
unknown hosts keep the established NVIDIA evaluator. Discovery is not runtime
certification: candidate encoding and all preservation/quality checks still run.
Physical AMD/Intel evidence remains outstanding. All 810 regression tests passed
remotely, including routing parity for explicit/automatic and mixed hosts.

### Old search decisions must not block the improved search

The shared evaluation-policy identifier now changes with the native-DV and
sample-refinement search. Previously cached automatic skip decisions from the
old policy can be evaluated again when the folder is submitted under this build.
Active jobs, explicit keep choices and completed replacements remain protected;
this does not modify an existing production queue or automatically start work.
The shared DV plan also records its evaluation policy for history readers.
All 811 regression tests passed remotely, including migration from the actual
previous policy and preservation of active/explicit-keep history.

### FEL integration and current-tool compatibility

The optional native renderer now evaluates every frame of a real FEL excerpt
and retains the complete enhancement payload and ordered metadata. Streaming
comparison agrees with lossless-render references without storing reconstructed
video intermediates. The ordinary automatic CLI passed with the current image's
FFmpeg 8.0.1 and NVIDIA encoder: the 246-frame output was 55.56% smaller and passed
both native and fallback quality checks. This is sample evidence, not a forecast
for the full movie. All originals remain unchanged; output copies do not count
as reclaimed library space.

The pinned runtime passed isolated dependency and cancellation checks. Docker
wiring is prepared but not yet image-qualified or deployed. Full-source trial
reuse avoids repeated encoding only after hashes and complete validation evidence
are rechecked. Broken excerpt decoding now falls back to the unchanged source,
without accepting the broken excerpt. See [FEL research](fel-research.md) for
runtime details, scores, and packaging limits. AMD/Intel physical work is deferred
by the Phase 1 NVIDIA-only scope.

Mixed MEL/FEL routing now selects full reconstruction rather than rejecting the
mixture; missing inventory cannot silently select MEL. All 842 regression tests
passed remotely after this change. The synthetic alternating-frame runtime check
also passed all 246 frames, with native candidate scores of 95.41 mean and 92.67
fifth percentile. This is renderer-path evidence, not full-file certification of
every mixed title. No production app or queue was changed.

### App result parity

A result-reader audit found the app still rejected validated MP4/MOV outputs,
although the shared engine and publisher already supported them for preservation
cases. App and publisher now use one container-evidence contract. Native outputs
require an explicit matching container field; unsafe paths and missing hashes
still fail. Explicitly copy-only results remain available with a qualification
explanation rather than starting a publisher that must reject them. The complete
remote suite passed 844 tests, including invalid-evidence and no-publication
coverage. No production queue, deployment or original media was changed.
