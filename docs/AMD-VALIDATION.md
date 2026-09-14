# AMD validation — 2026-09-08

Local device: Radeon RX 7800 XT; Windows driver 32.0.31041.1004.
FFmpeg/FFprobe: installed 8.1 essentials build. Tested current source after
pulling main at 7b71ac1; no driver/software installs or source-media changes.

## Fresh execution results

Two-second generated SDR H.264 MKV fixtures, 24 fps, B-frames, two AAC tracks
and one SRT subtitle track. Encoded serially through workflow_worker with AMD
quality QP I=21/P=23 and original dimensions. These are functional checks, not
real-movie quality measurements or evidence for every AMD adapter.

| Input | Encoder | Result |
| --- | --- | --- |
| 1920x1080, 8-bit | hevc_amf | Passed stream/timing, copied track and full output decode validation |
| 1920x1080, 8-bit | av1_amf | Rejected by strict geometry gate: 1920x1082 coded picture with two padding rows; crop-aware FFmpeg displays 1920x1080, player compatibility pending |
| 3840x2160, 10-bit SDR | hevc_amf | Passed stream/timing, copied track and full output decode validation |
| 3840x2160, 10-bit SDR | av1_amf | Passed stream/timing, copied track and full output decode validation |

The 1080p AV1 issue reproduced with generated MP4 and MKV sources. The immediate
cause of the geometry gate is coded padding plus container crop metadata.
Whether other drivers/builds behave differently remains untested. No scaling
or validation bypass was applied.

Additional observed gates:

- Incomplete source color signaling blocks conversion; explicit x264 bitstream
  color parameters were needed for the tagged test fixture on this build.
- Generated MP4-to-MKV jobs were rejected for audio format/time-base differences.
  This is not proof of corrupted audio; the ordinary worker's conservative
  comparison does not accept that container clock change.

## Evidence and limits

Dashboard log: reports/job-20260908-113610-8c4491d0/terminal.log.
Generated media and per-job validation live outside OneDrive under the local
Codex workspace, in amd-validation-20260908-113610-85a2aa47. Other preliminary
fixture attempts were retained separately. No media was deleted in this run.

Previous real-media HEVC and Dolby Vision 8.1 tests passed playback review,
but this run did not retest HDR/Dolby Vision, AV1 perceptual playback, full AV1
episodes, other AMD models, or sustained-load stability. The AMD test effort
is not universally complete while the 1080p AV1 mismatch remains unresolved.

## Alignment investigation

The rejected file reports 1920x1082 with stream-level Frame Cropping metadata
requesting crop_bottom=2. FFprobe's decoded frame reports 1920x1082 with
zero frame crop, but FFmpeg's CLI also applies container cropping (see below).
Separate 12-frame tests of `-align none` and `-align 1080p`
both reproduced it; strict `-align 64x16` emitted a resolution error and no
usable output. Thus changing the alignment option is not a verified fix here.
FFmpeg exposes these AMF alignment/crop mechanisms in its encoder source:
https://www.ffmpeg.org/doxygen/8.0/amfenc__av1_8c_source.html

The worker now explains the observed dimensions and explicitly offers HEVC or
retaining the source. It does not blacklist all AMD AV1: exact-size 4K passed.
No scaling, bitstream rewriting, driver installation or automatic fallback was
added. Player-specific crop handling requires separate validation; claiming
1080p preservation based only on crop metadata would weaken the current gate.

The ordinary worker still rejects the padded 1080p AV1 output. The later Sony
Direct Play result below is player-specific evidence, not a validator change.

### Container-aware decode follow-up

All 48 frames of the rejected two-second AV1 fixture were decoded to frame MD5
records without writing video. FFmpeg's default behavior and explicit input
`-apply_cropping all` both produced 1920x1080. Their complete frame records
matched decoding with `-apply_cropping none` followed by removal of only the
two bottom padding rows (`crop=1920:1080:0:0`). No scale filter was used.
With cropping disabled and no filter, decoded geometry was 1920x1082.

SHA256 of newline-joined frame records (timestamps, sizes and frame MD5s):
`b5b35c20727d38143359bc0b2912723c50ffa45bcb06a63c70a18d4a9f4cc3be`.
This proves equivalent handling of the encoded picture in the tested FFmpeg,
not lossless equivalence to the pre-encode H.264 or universal player support.
FFmpeg documents the separate codec/container cropping choices at
https://ffmpeg.org/ffmpeg.html (apply_cropping).

A 30-second video-only loop of that generated fixture was stream-copied to
`test-output/AMD-AV1-1080p-Padding-Diagnostic-20260908.mkv` for player testing.
It is deliberately labeled diagnostic, is not a validated production output,
and has no audio. No original media was used. On 2026-09-08 the user reported
successful playback. The subsequent Plex dashboard screenshot identifies Plex
Web in Chrome on localhost, with 1080p AV1 (hw) input transcoded to 1080p H.264
(hw). This confirms user-approved playback through Plex's hardware-transcode
path, not native AV1 crop handling or Direct Play/Direct Stream compatibility.
The worker's conservative rejection remains enabled.

### Sony Direct Play follow-up

The user reported the video-only diagnostic stalled on the Sony. A generated
H.264 MP4 control with silent AAC stereo then Direct Played on both Chrome and
Plex for Android (TV), identified as BRAVIA 4K VH2 in the dashboard.

A separate `test-output/AMD-AV1-1080p-With-Audio-20260908.mkv` was made by
copying the diagnostic AV1 video and adding silent AAC stereo. All 720 video
packet hashes and packet timestamps/durations matched the video-only clip;
stream dimensions, time base and crop metadata also matched. Full video/audio
decode passed. Neither input nor source media was modified.

The user's subsequent screenshot shows BRAVIA 4K VH2 Playing at 0:11 / 0:30,
with both 1080p AV1 video and AAC stereo audio marked Direct Play. This confirms
native delivery/playback startup of this padded AV1 fixture on that client.
The result points to video-only handling as the likely cause of the earlier
stall, but does not isolate an app defect or prove pixel-exact crop rendering,
full-clip completion, general AMD compatibility, or real-media visual quality.
No automatic silent-track insertion or geometry-check relaxation was added.

## Real-media playback and AV1 tuning follow-up

The Battlestar S02E20 short diagnostic with the original DTS-HD MA / AC3 audio
and PGS subtitle tracks played successfully per user review. The Sony BRAVIA
4K VH2 dashboard showed Direct Play for AV1, DTS-HD MA and PGS without changing
settings. Chrome instead hardware-transcoded video, transcoded audio and burned
PGS subtitles. These are client-specific playback results, not universal support.

The initial AV1 QP21/23 diagnostic increased video bytes by 58.83%. The shared
AMF options currently reuse HEVC-style values for AV1. AMD's AV1 API documents
a different QP range (1–255), so codec-specific calibration is needed:
https://github.com/GPUOpen-LibrariesAndSDKs/AMF/blob/master/amf/doc/AMF_Video_Encode_AV1_API.md

Serial QP I=P trials against the same 31.282-second SDR reference:

| AV1 QP | Total file bytes | Total savings | Sampled VMAF |
| --- | ---: | ---: | ---: |
| 80 | 49,927,260 | 63.17% | 95.95 |
| 100 | 27,252,019 | 79.90% | 93.72 |
| 120 | 19,588,970 | 85.55% | 90.94 |

All three preserved the 3,864 audio and 42 subtitle packet signatures/timing,
color fields and 746 decoded frame timestamps (within 2 ms). Coded geometry
remains 1920x1082 with only two bottom padding rows. VMAF compared container-
cropped 1920x1080 pictures without scaling, using frame-index alignment after
checking decoded timestamps and sampling every sixth frame. The copied
reference contains two non-displayed open-GOP packets; production validation
was not relaxed to accommodate the diagnostic cut.

QP80 was copied to the Plex test folder for visual review as the highest-scoring
space-saving trial. The user subsequently reported it plays well; the Sony
dashboard showed Direct Play for AV1, DTS-HD MA and PGS subtitles. This is the
reviewed five-minute scene only, not full-episode approval.
Scores on one scene are ranking aids, not proof of visual
transparency or whole-episode savings. Production quality defaults and geometry
gates remain unchanged pending broader validation. Source episode size and
mtime still match the recorded fingerprint. No media was deleted in this run.

Evidence: reports/amd-av1-tuning-20260908-144208-c703d0ac.json.

### Three additional QP80 scenes

Eleven three-second read-only probes across the original episode selected
15m (lowest luma), 45m (largest frame difference among remaining probes), and
55m (highest luma entropy among remaining probes). Labels Dark/Motion/Detail
are numeric candidate labels, not confirmed visual scene classifications.
Each extracted reference is approximately 30 seconds, with keyframe lead-in.

| Candidate | Total savings | Sampled VMAF | Decoded frames |
| --- | ---: | ---: | ---: |
| Dark, 15m | 64.35% | 93.68 | 746 |
| Motion, 45m | 73.87% | 95.73 | 731 |
| Detail, 55m | 53.90% | 94.14 | 741 |

All passed decoded frame-count/timing comparisons and identical audio/subtitle
packet checks against their copied references. Original audio decoded without
errors, and both videos decoded for comparison. Color signaling was unchanged;
the AV1 padding/crop behavior remains as above. No scaling or production gate
changes. Original source size/mtime unchanged after the run. All three copies
were placed in test-output with Dark-15m, Motion-45m and Detail-55m in filenames
(no "sample" naming). User playback/visual review is pending for these scenes.

Reports: amd-av1-tuning-20260908-144954-677d06bd.json,
amd-av1-tuning-20260908-145027-476df6e8.json,
amd-av1-tuning-20260908-145057-3e6e96dd.json under reports.
Selection metadata and references remain outside OneDrive under local workspace
amd-scene-checks-20260908-144944. No files deleted.

## Standalone opt-in route and second-episode check — 2026-09-09

`python/amd_av1_preview.py` now exposes a bounded, dry-run-by-default standalone
QP80 preview route. See AMD-AV1-PREVIEW.md. Encoder preset selection is explicit
and rejects non-AMD, non-AV1, HDR, Dolby Vision, 10-bit and uncalibrated quality
modes. The default optimizer and strict geometry gate are unchanged. The new
geometry validator permits exact dimensions or only the two-row bottom-padding
case, requires square pixels/no rotation, and checks every decoded frame at
1920x1080. No source deletion or replacement option exists in the preview CLI.

204 root tests passed, including seven new tests for preset isolation, invalid
crop/resize/rotation cases and side-effect-free dry-run. Test temporary files
were placed on E. No Git actions or software installs were performed.

Fresh S02E19 preview at 15 minutes: 728 decoded frames, 3,773 identical audio
packet signatures across two tracks, 59 subtitle packets across three tracks,
full output decode passed, color fields unchanged, 77.06% total size reduction.
Every decoded displayed frame is 1920x1080 despite coded 1920x1082 plus crop.
Original size/mtime unchanged; no full-source hash comparison claimed for this
preview. New reference, output and validation live under:
`E:\MuxMender-TestOutputs\AMD-AV1-QP80-20260909-130434-9c3dfcc6`.
The user confirmed on 2026-09-09 that S02E19 playback tests passed on both
Chrome and the Sony TV. Delivery modes for this specific clip were not supplied;
do not infer Direct Play from playback success alone. This one clip does not
establish whole-episode savings or support for other AMD models.

## MP4-to-MKV audio investigation (continued)

Full decoded-frame inspection of the generated 1080p fixture established a real
priming difference, not just a time-base rounding mismatch. For audio track 0:

- MP4: 94 decoded frames / 96,256 samples; first decoded PTS 0.
- MKV: 95 decoded frames / 97,280 samples; first decoded PTS -0.021.
- The MP4's first packet contains Skip Samples=1024; the MKV first packet lacks
  that side data. Payload equality alone therefore does not prove equivalence.

The worker now rejects changed packet side data before trying duration rounding,
with an explicit priming/padding diagnostic. Regression coverage ensures this
case cannot become an accepted rounding adjustment. No validator relaxation,
audio re-encoding or source modification was applied.

A container-preserving or proven priming-preserving mux route is needed before
this MP4/AAC case can pass. Do not force MKV, drop samples manually, or accept
the extra decoded audio based only on its short duration.
# Reusable runner validation — 2026-09-09

`amd_av1_preview.py --full` now provides the opt-in full-file copy route.
A five-second explicitly tagged H.264/AAC synthetic input passed on this AMD:
120 decoded frames, 1920x1080 displayed geometry, matching original SHA-256,
copied audio packet verification and 59.40% total savings. This is integration
coverage, not a perceptual-quality result for real episodes.

A read-only AMD plan found ten Band of Brothers metadata candidates. Episode 1's
30-second excerpt passed output decode and copied-packet comparisons (67.12%
savings), but source extraction emitted EBML/container-boundary warnings. It is
**not approved for full-file conversion**. The runner now rejects those warnings;
the E: run directory includes a superseding `source-review-required.json` record.
No media on Y: was written, renamed or deleted during these tests.

Episode 2 also emitted packet-truncation/invalid-EBML-length warnings while
extracting its preview. Its otherwise passing excerpt checks (65.77% savings)
do not clear the source for conversion. These additional warnings now stop the
runner as well. Both preview reports are marked source-integrity-review-required.
The final root unit suite passed 208 tests; the full-file synthetic integration
also passed after enabling strict FFmpeg error handling.
