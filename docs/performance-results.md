# Faster processing: measured results

## PQ quality scoring follow-up (2026-10-03)

Six balanced two/four-worker runs on generated footage kept every per-frame
metric identical. Median scoring time for 720 1080p frames was 42.25 seconds
with two workers and 29.77 with four. For 120 4K frames it was 27.30 versus
17.27 seconds. These measure the scoring stage only, not a complete conversion.
The decoder and existing common HDR rendering were unchanged; this is not a
new certification of a native HDR perceptual metric.

The shared workflow uses four PQ scoring workers only with CPU/task headroom
and at least eight GiB available memory. Unknown or pressured resources and
untested profiles use two. Shared admission also bounds the final allocation.
Peak memory for the 4K test increased by about 0.4 GiB.


The corrected shared workflow finished the two-file benchmark in **35.44 minutes
instead of 56.55 minutes**: **37.33% less observed elapsed time**, with unchanged
quality, metadata, timing and savings requirements.

The full conversion passed automatic validation and produced a test copy
**75.18% smaller**, with the same encoder selection and size as the baseline.
The other file correctly kept its original. Neither original was replaced.
These are research results, not a deployed release or reclaimed library space.

## Final comparison

| Measurement | Baseline | Corrected adaptive workflow |
|---|---:|---:|
| Two-file batch elapsed | 56.55 min | 35.44 min |
| Recorded GPU-priority pause in longest job | 5.40 min | 0 min |
| Elapsed excluding that recorded pause | 51.15 min | 35.44 min |
| Encoding, including trial clips | 990.29 s | 620.64 s |
| Complete frame validation and trial frame checks | 1604.13 s | 1052.36 s |
| Quality scoring | 273.30 s | 163.57 s |
| Copied-track verification | 97.91 s | 46.28 s |
| Other complete decoding | 55.64 s | 55.49 s |
| Checksums | 36.41 s | 37.71 s |

Stage timings are for the full-conversion job, not aggregate CPU time. Batch time
includes admission waits. Removing the explicitly recorded baseline GPU pause
leaves **30.71% less elapsed time**; it does not remove cache, order or other
shared-host load effects. Runs used the same host, inputs and settings, in
baseline-then-candidate order, rather than a randomized hardware benchmark.

An earlier fixed-four-worker experiment completed in 35.61 minutes. Its agreement
with the final adaptive result is encouraging, but neither result establishes a
universal speedup across codecs, HDR workflows, storage systems or busy hosts.

## What is implemented

- Bound previously implicit FFmpeg worker pools and generated capability probes.
  Explicit decoder compatibility and thread options remain intact.
- Choose two or four workers for the measured progressive eight-bit H.264/HEVC
  SDR path, using container CPU allocation, host load, task headroom, memory and
  storage pressure. Unknown measurements or pressure retain two workers; other
  media keeps its existing path rather than being rejected.
- Use selected packet reads for at most two copied tracks, avoiding unused
  re-encoded-video hashes. Larger track sets retain a combined pass. Complete
  packet hashes, timing checks, independent duration-header evidence and strict
  decoding remain mandatory.
- Coordinate CPU validation and GPU stages with bounded admission, preserve
  other applications' GPU priority, and report resource waits and GPU pauses
  separately from processing.
- Improve live development progress reporting and package the shared GPU-activity
  and pause modules in both entry points. Container reaping is prepared for the
  next image; see the deployment limits below.

The SDR resource policy retains a six-GiB available allocation requirement,
direct host headroom or the existing bounded ARC-reclaim proof, a 50% host-load
ceiling, six spare allocated CPUs, and task/I/O/memory-pressure checks. Installed
RAM and the entire ARC are not treated as immediately free. Worker count is
selected at stage launch; it is not a live resizing mechanism for an active
FFmpeg pool. GPU-sharing suspension remains separate.

## Evidence that the results stayed equivalent

- Both final cases exited successfully with the same baseline outcomes.
- All **76 sample records** matched in size, reported metrics and validation
  verdicts. Rejected trials are included; this does not mean every sample passed.
- Both codec selections and processing plans matched, except for the added
  worker-policy label. Sample paths and encode wall time were excluded from
  sample-record comparisons.
- Complete source-frame evidence matched byte for byte: **34,853,876 bytes**,
  identical SHA256, empty reader error log. It was checked only after the source
  reader exited; file identity stayed stable during hashing.
- Full output passed frame, metadata, copied-track, strict decoding and checksum
  validation. Source SHA256 matched the baseline.
- Output size matched exactly: **2,952,899,086 bytes** from **11,898,719,149 bytes**.
  Container checksums differed, so byte-identical containers are not claimed.
- The frozen run matched all **228 local Python/test files** checked, with no
  remote manifest mismatch. No running code was edited.
- **103 Linux tests passed** before media processing. Separate suites passed
  25 Linux process/admission tests, 20 cancellation/cleanup fixture tests, and
  17 Linux monitor tests. These scopes are not summed as unique test coverage.
- Originals stayed read-only in research; production was not resumed or deployed.

The full result remains a validated research copy awaiting optional playback,
not authorization to publish or replace a source.

## Tradeoff: a short job can wait longer

The no-benefit case took **1,066.53 seconds versus 412.09 seconds**. It spent
597.83 seconds waiting for GPU admission and 92.91 seconds waiting for validation.
Its complete batch still finished sooner, but individual latency did not improve.
Do not advertise the batch improvement as a per-file latency guarantee. Resource
fairness and shared-host responsiveness remain priorities.

The initial invalid benchmark's slower candidate was also audited: 23 matching
samples totaled 678.56 versus 857.96 seconds, with identical output sizes.
Nine baseline samples and twelve candidate samples had roughly 60-second stalls.
Those three additional stalls account for almost the entire 179.39-second gap.
That runner inherited production's GPU-pause lease. Saved progress shows abrupt
elapsed-time jumps, but historical lease decisions were not retained, so exact
pause attribution cannot be proven retrospectively. Corrected runs use their own
ownership-aware lease and explicit pause accounting.

Concurrent capability failures were separately reproduced as thread-creation
failures under container task pressure: six serial probes passed, three of six
concurrent probes failed, and 24 bounded-thread serial/concurrent probes passed.
This is not proof that every historical CUDA failure shared that cause.

## Other options tested

| Option | Evidence | Decision |
|---|---|---|
| Four-worker SDR quality scoring | Five scenes; all frame hashes/timestamps and per-frame/pooled scores matched; 107.36 to 55.52 seconds | Integrated within the measured adaptive scope |
| Selected copied-track reads | Two-track full-source repeats; 570,664 audio and 1,088 subtitle packets matched exactly; about 62 to 18 seconds | Integrated for small track sets |
| Faster HDR frame-threaded reader | One full source matched all 169,457 frame records, but a known regression changed metadata on 200/497 or 300/497 frames in repeated tests | Not enabled; retain slice reader |
| Direct NVIDIA H.264 decoding | Five scenes took 38.35 seconds versus 35.16 on CPU; serialized timing differed | Not enabled as a drop-in optimization |
| Persistent cross-run validation cache | Needs content/policy-bound evidence, durable recovery and additional disk retention | Deferred; existing checksummed within-run reuse retained |

Raw-picture hashes also differed in the NVIDIA experiment, but pixel layout was
not normalized. That does not establish visual corruption or a generic NVIDIA
decoder defect. Short CPU decoded-frame hashing showed essentially no gain
(34.26 versus 34.10 seconds), despite faster quality scoring.

## Native GPU HDR inspection research (2026-10-02)

The isolated RTX 5050 reader uses the upstream FFprobe JSON serializer and
native HEVC metadata parser with GPU decoding. It reads metadata directly from
hardware frames: it does not download or rescale pictures, change HDR values,
or replace quality scoring.

Three alternating CPU/GPU trials on a 240-frame, 4K HDR10+ excerpt took a median
**12.986 seconds on CPU and 0.946 seconds on GPU**: about 13.7 times faster for
this inspection, not for the whole conversion. The shared validator confirmed
every HDR field, timestamp, geometry and color field against both the isolated
CPU reader and the installed CPU baseline. All 240 frames carried matching
static and dynamic HDR metadata.

The initial GPU reader missed four deliberately damaged inputs. The revised
experiment checks slice entry-point bounds and waits for NVIDIA's decode status,
rejecting errors even when the driver conceals them. It rejected all seven
generated damaged/truncated inputs; six also produced CPU errors, and the
remaining concealed-error case was rejected by GPU alone. The healthy fixture
decoded cleanly to all 48 frames on both readers.

The read-only whole-file GPU inspection reached EOF in **369.424 seconds**
(6 minutes 9 seconds), with an empty error log. It returned **149,241 frames**,
matching a separate full-source packet count. All frame records passed the
shared consistency checks, including static/dynamic HDR presence, progressive
geometry, color fields and monotonic timing. The installed CPU excerpt also
matched the corresponding records from the whole-file GPU read exactly.

The previous production CPU inspection hit its 120-minute stage limit near EOF.
That is not a completed paired CPU benchmark, so it is not an exact full-file
speedup ratio. Source size and modification time remained unchanged; the
research source mount was read-only. The 411,409,514-byte full-frame manifest
and all generated malformed media were removed, leaving compact evidence.

This research is **not enabled in production** and is not full-file CPU/GPU
pairwise metadata certification. It does not authorize replacement or weaken
any quality gate. These measurements concern HEVC source inspection, not
complete conversion time, output quality scoring or an AV1 GPU reader.

### AV1 follow-up

The isolated AV1 extension passed the generated 10-bit PQ control and a static
HDR control, with all 48 frame records matching the installed CPU reader's
metadata, timing, geometry and color fields. Static mastering-display metadata
was present on every frame. The initial fixture omitted transfer/primaries on
both readers; setting those declared test properties on the generated input
frames corrected the fixture without relaxing validation.

All seven deliberately damaged/truncated AV1 inputs were rejected. Four also
produced CPU errors; three produced concealed-error status on GPU even though
the CPU error log was empty. Driver completion/error status worked for AV1 on
this tested RTX 5050/driver combination; support must not be assumed on other
driver or hardware combinations.

On the two-second 720p control, GPU startup cost made inspection slower than CPU
(roughly 0.46 versus 0.21 seconds). Three alternating full reads per backend of a
generated 30-second 4K, 10-bit PQ clip took median **12.421 seconds on CPU versus
2.721 seconds on GPU**: about 4.6 times faster, or 78.1% less inspection time.
All 720 frame records matched the shared timing/color/geometry validator on
each paired trial. This is inspection speed, not complete conversion speed.
Dynamic HDR and a long real-file AV1 read remain unqualified. No AV1 production
reader is enabled, and generated video/elementary-stream fixtures were removed.

## Next-build limits

The implementation and research qualification are complete for the stated scope.
No quality threshold, full-frame requirement or publication gate was weakened.
A release still needs separate approval and final image-level smoke testing,
including its PID-1 reaper. The isolated reaper test does not certify that final
image. Existing research containers with non-reaping PID 1 are not repaired by
source changes; recreate them only after work has drained and with approval.

No deployment, git publication or source replacement was performed. See the
[qualification work list](performance-qualification-plan.md) for the task audit.
# Shared reader preparation and exact static-metadata reuse

## Whole-file real AV1 result

The isolated RTX 5050 run completed both whole-file reads of a 157.8-minute,
3840×1600, 10-bit AV1 HDR10 source. CPU inspection took 2,430.92 seconds;
native GPU inspection took 518.48 seconds: **78.67% less inspection time**,
about **4.69× throughput** for this stage on this source.

All 227,064 frames matched in static HDR, color/geometry, chroma and exact
timestamps. Both readers reached clean EOF. A subsequent generated-control run
against the same immutable executable rejected all seven damaged inputs, with
no false passes. A before-GPU read-only-mount digest witness and the later control
digest identify the same executable; the historical frozen report is retained
unaltered. Source identity stayed unchanged. The run removed 554,887,354 bytes
of temporary frame manifests and retained only small research evidence.

An attested AV1/static-HDR reader artifact with pinned sources and licenses is
prepared outside the repository. It is not deployed, is not a whole-conversion
speedup result, and grants no perceptual-quality or replacement authorization.
The separate static-HDR HEVC comparison also passed: CPU 2,264.44 seconds versus
GPU 257.25 seconds, **88.64% less inspection time**, with 109,681 frames matching
in HDR metadata, geometry/color/chroma and exact timestamps. Both readers drained
cleanly to EOF, source identity was unchanged, and 269,432,216 bytes of temporary
manifests were removed. Fresh same-build HEVC controls passed and rejected all
seven deliberately damaged inputs, including a case the CPU reader accepted.
Dynamic HDR AV1,
HLG, other pixel layouts, other hardware/driver combinations and final image
integration are not certified by this AV1 result.

The generated 61-second shared-engine reader test passed with 1,464 frames and
exact timing/color/geometry. It exercised `Workflow.frame_file`, taking 4.30
seconds on CPU and 1.96 seconds with the qualified research GPU profile. Its
39,450,138 temporary bytes were removed. This is an integration fixture result,
not library throughput or image-owned profile-loader certification. Complete
generated conversion/quality/savings checks subsequently passed: 1,464 output
frames, unchanged source checksum, VMAF mean 98.89 and fifth percentile 96.84,
self-calibration passing, and a 37.65% smaller generated copy (60,022,895 to
37,421,836 bytes). The exact shared CPU/native command dispatch was recorded.
This uses the existing 90/90 quality floors and fixed 25% fixture savings
requirement. Quality was measured through the existing common HDR-to-SDR render,
not a native-HDR perceptual model. It is not a real-library end-to-end speedup or
replacement authorization. The real HDR10+ whole-file pair also passed: all
149,241 frames matched exactly in static/dynamic HDR metadata, timestamps and
geometry/color/chroma. Both readers drained cleanly to EOF and source identity
was unchanged. CPU inspection took 7,191.08 seconds (1h59m51s), versus 369.57
seconds (6m10s) on the GPU: **94.86% less inspection time**, or 19.46 times the
inspection throughput in this pair. All 149,241 frames contained matching
HDR10+ and static metadata. The run removed 826,770,676 bytes of temporary
manifests; a subsequent read-only check found no remaining frame manifests.
Balanced excerpt rounds and same-build damaged controls support the result,
but this is one full-file CPU-then-GPU pair, not a whole-library or complete
conversion speedup. No quality or replacement authorization follows from it.

A read-only ten-second sample during that CPU baseline used 0.998 CPU-core
equivalents despite four reader threads and an eight-core container quota.
Reader RSS was about 247 MiB under an 8 GiB memory limit, with zero physical
disk-read bytes during the sample. This points to CPU reader work rather than
RAM capacity or physical read pressure in that interval; it is not a full-run
utilization average. It supports testing the GPU reader, not promising that
more RAM or a larger thread setting would speed this particular stage.
A separate five-second limit check recorded no CPU throttling, about 305 MiB
total container memory usage, and zero recent CPU/memory pressure averages.
Container limits were not constraining that observed interval.

Automatic and preservation HDR callers now use the same full-reader command
builder. Short samples avoid reader-package lookup costs. Qualified GPU stages
carry actual codec/geometry context into adaptive admission, so decode work is
not learned as an unrelated encode stage. The packet-position-only brightness
mapping path remains on its existing CPU reader until separately qualified.

Research HDR comparison no longer performs a duplicate chroma/timestamp scan:
the shared validator already checks both on every frame. Qualification still
requires its exact-timestamp result, stricter than ordinary container-rounding
preservation. Tests reject even a one-millisecond reader difference, changed
chroma and missing frames. A receipt builder refuses incomplete whole-file
evidence, a different reader build, escaped damaged inputs or no measured benefit.

The shared automatic engine now dispatches complete HDR frame reads through an
image-attested GPU reader when its qualification scope matches. The receipt and
reader must be root-owned, non-linked, and not writable by other users. The
receipt binds the executable SHA256, visible GPU UUID, driver and device
visibility, and requires full EOF, every-frame CPU/GPU equality, damaged-input
rejection and a measured speed benefit. Missing, mismatched or unsupported
qualification keeps the existing CPU reader; it does not reject the video.
Decode errors from a selected reader propagate without a silent CPU retry.
Dolby Vision header side data retains CPU inspection: these ordinary HDR
comparisons do not attest Dolby Vision frame-reader parity. This is a reader
choice, not a new video rejection rule or a change to the separate Dolby flow.
No receipt is published yet, so this dispatch is not enabled in production.
Container selectors `all` and the attested sole GPU UUID are treated as
equivalent only after confirming that exactly one matching physical GPU is
visible with the qualified driver. CUDA logical masks and ordering still must
match. Numeric indices, device lists and disabled selectors are not normalized.
This avoids confusing a deployment spelling difference with different hardware;
it does not qualify a new card or driver. See
[NVIDIA's GPU enumeration documentation](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/docker-specialized.html).

The latest frozen Linux control snapshot passed 65 tests covering shared dispatch,
attestation policy, GPU admission, OS lock release, owned-worker pause/cancel,
supervisor-death cleanup, strict HDR metadata failures and tracked early
qualification failures. Integration success is now recorded only after owned
temporary-file cleanup and report persistence; simulated failures of either
operation leave a failed job, never a completed one. The generated shared-engine
test and fresh HEVC damaged
controls have passed, as reported above. They ran serially to keep GPU timing
measurements separate. The generated test explicitly injects the qualified
research profile; it does not certify image installation. Earlier unstarted
image-test contexts were retired. The r7 isolated context passed with completed
AV1/static-HDR HEVC/HDR10+ receipts, cleanup-result reporting and explicit Tini
subreaping in its shared PID namespace. The latest post-fix Linux regression
run again passed all 65 tests. The test mounted no library media and did not
change the production app or queue.

The first installed-image launch completed with a failed loader check before
fixture generation. Its executable checksum, permissions, GPU UUID and driver
matched. Docker exposed the qualified GPU through its device request while the
image reported `NVIDIA_VISIBLE_DEVICES=void`. The selector check now accepts
this configuration only after confirming exactly one visible adapter with the
qualified UUID and driver; CUDA masks and device ordering still must match.
Regression checks reject absent, multiple, different and driver-changed adapters.
The refreshed r7 isolated test passed. The image-owned loader accepted the
receipt, and shared source/output inspection dispatched the native reader.
All 1,464 generated frames matched, with zero timestamp differences. CPU
inspection took 6.6616 seconds versus 2.0243 seconds on GPU, 69.61% less time.
The complete generated conversion passed preservation, quality (mean 98.8882,
fifth percentile 96.8411), source-integrity and the existing savings policy.
Its 60,022,895-byte input became 37,421,836 bytes, 37.65% smaller. Cleanup removed
101,922,948 temporary bytes before publishing completion. The whole generated
test took 122.48 seconds, including 101.22 seconds in quality measurement.
This verifies image integration on the qualified GPU/driver; it does not measure
whole-library conversion speed or native-HDR perceptual quality. The installed
production app still requires an updated release containing the reader bundle.

The real AV1 whole-file comparison first reached the research reader's
30-minute limit during its CPU baseline. That is incomplete qualification,
not evidence of a bad picture or a GPU failure. The retry has an explicit
90-minute research allowance per reader and reports current-stage ETA.
Production processing limits and quality thresholds are unchanged.

Shared frame readers now have the same owned-process pause interface used by
other media stages. Explicitly activated native GPU frame inspection is admitted
through the GPU resource pool; its filename alone cannot enable that route.
These changes prepare integration, but do not enable GPU frame reading in the
installed app. Mocked cancellation tests never signal the Windows host. Nine
live Linux control tests subsequently passed inside the isolated research
container, including paused-reader cancellation/reaping, pause time excluded
from the processing budget, expiry/resume, and supervisor-death cleanup. These
use only owned synthetic workers, not library media or competing GPU processes.

Exact mastering-display fraction normalization now uses a bounded 256-value
cache. Only immutable numeric values are reused: no frame, outcome, corruption
check, or replacement approval is cached. Dynamic metadata is still checked
frame by frame. A synthetic Windows microbenchmark (20,000 static metadata
records, median of three runs, identical results asserted) measured 0.385 seconds
without reuse and 0.0364 seconds with reuse, about 90.5% less time for this
operation. This is not an end-to-end conversion performance claim.
