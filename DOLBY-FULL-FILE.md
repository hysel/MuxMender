# Experimental full-file Profile 8.1 workflow

Final regression and handoff status is in [NVIDIA-HANDOFF.md](NVIDIA-HANDOFF.md).
The updated pipeline subsequently passed a complete bounded DV regression and
60/300-second sparse/empty-track stress tests. Earlier failures below remain
historical evidence; they are not the latest run status.

## 65 full-file playback failure and interleaving investigation

The corrected ordered remux was subsequently approved by the user on both
Chrome and Sony TV: seeking works on both, and Dolby Vision mode and sound sync
are correct on the TV. Evidence is in
`reports/nvidia-dv-full-65/dv-full-20260906-085358-cbfa0f53/ordered-remux-20260906-103728/validation.json`.
Video packets/timestamps, original audio/subtitles, chapters and video metadata
matched; five seek-point ordering checks passed. This approves that repaired
full file on the tested clients. Historical failures remain documented. The
new end-to-end code and sparse/empty-track coverage remain separate validation
work before general NVIDIA DV enablement. Original media on Y remains active.

The first full NVIDIA 65 output passed structural checks and saved 33.97%,
but the user reported slow Chrome seeking and a Sony TV client crash. The
restored original seeks successfully. The failed copy on Y was deleted only
under explicit user authorization; the original and local diagnostics remain.

Seeking near 27 minutes in the failed output exposed over 41 seconds of video
packets without audio. A separate-track remux with the normal finite interleave
timeout improved that point but failed others. An experimental remux with
premature queue flushing disabled passed five seek-point ordering checks;
packet preservation and device playback review are separate acceptance steps.
TV crash causation is not yet proven. NVIDIA DV remains experimental.

Future explicit NVIDIA full-file runs first put injected video into a timestamped
video-only container, then copy it with original tracks into the final container.
This DV experiment uses `-max_interleave_delta 0`; it is not a general optimizer
default. Memory behavior with other sparse/empty track combinations still needs
coverage. Six bounded seek-point checks now reject missing/late audio as well as
startup interleaving errors. The additional retained timestamped video copy is
included in the post-encode space check.

## NVIDIA 65 sample playback approval (2026-09-06)

The 30-second scene near five minutes in 65 (2023) passed user playback
review: synchronized sound/video, Dolby Vision confirmed, and visual quality
approved in response to the Sony TV test request. Video payload savings were
53.29%; this is not a whole-file savings prediction. Automated checks passed
for all 719 frames, including timing, parsed RPU content/order, static HDR,
3840x1604 resolution, 10-bit BT.2020/PQ, audio/subtitles, and sample decoding.
Encoding ran at approximately 1.58x. Evidence:
`reports/dv81-20260905-232311-50a119f5/validation.json`.

Full-file NVIDIA DV validation remains pending. The earlier Acolyte failure
is unresolved; the normal AMD-only preservation gate remains unchanged.

## Current acceptance policy and Sony TV result

The goal is smaller files with acceptable visual quality and preserved tracks/
metadata. Larger or equal-size outputs are never accepted as optimizations,
including when minimum savings is set to zero. Default minimum savings is 5%.
Quality is not lowered automatically to force a saving; an unsuitable source
is skipped and its original retained.

Before a full experimental NVIDIA DV encode, an automatic 30-second sample
must pass preservation checks and show video-payload savings at the configured
threshold. The completed container must independently meet the total-size
threshold before expensive final verification and publication eligibility.
The retained-output verifier also rejects oversized outputs immediately.

The user reported the full Acolyte output failed on the Sony TV: black screen,
playback clock not advancing. The report/dashboard now record playback failure;
automated structural success is retained as separate evidence. Its 179.38% growth
also disqualifies it. The full episode and previously tested oversized samples
were withdrawn from the Plex folder. Original media on Y was not changed.
Local diagnostic media and reports remain available for investigation.

Recent Plex statistics matching the episode duration show HEVC video copy with
audio/subtitle conversion, but do not establish filename identity or the client
failure cause. No decoder root cause is claimed. NVIDIA DV is not certified for
full-file use, and the normal AMD-only gate remains in place.

Historical research results below are not optimization or playback approval.

## Separate NVIDIA sample experiment (2026-09-05)

The normal optimizer and full-file preservation gate remain AMD-only.
`dv_preservation_test.py --experimental-nvidia` explicitly enables only a
1..30-second Profile 8.1 research sample. Default behavior remains AMD.
No CPU fallback, scaling, tone mapping, Profile 5/7 conversion, or extra
dynamic-HDR metadata removal is allowed. The sample checks reject HDR10+.

This initial NVIDIA sample uses HEVC Main10, p7/HQ VBR CQ18, with B frames
disabled to simplify the raw HEVC/RPU presentation-order experiment. These
are experiment settings, not new general optimizer defaults or AMD QP equivalents.
The existing RPU extraction/injection/content and frame-order comparisons are
retained, with additional stream/disposition, aspect-ratio and startup
interleaving checks. Audio and video are decoded. Sample chapters are omitted;
whole-file chapter preservation is not certified by this bounded test.

Prepared candidate: The Acolyte S01E07 on the media share, 3840x1608,
10-bit BT.2020/PQ Profile 8.1. Start near 300s, initially 10 seconds.
111 unit tests pass, including the unchanged full-file NVIDIA block.
Generated Main10 configuration test passes in
`reports/nvidia-dv-preflight-20260905-215337-5a50646f/validation.json`.
This generated pattern contains no Dolby Vision metadata. An initial pattern
lacked input color tags; the retained retry explicitly tags the input frames.

User approved portable dovi_tool 2.3.3. It was downloaded into the project's
`tools/dovi_tool-2.3.3` directory; archive SHA-256 matched GitHub's asset digest.
No driver changes or system PATH changes were made.
User must review playback on a Dolby Vision-capable device and confirm DV
mode before any broader NVIDIA preservation enablement.

## First NVIDIA Profile 8.1 result

The 10-second Acolyte S01E07 sample from the beginning passed in
`reports/dv81-20260905-215723-b1f12c28/validation.json`.
All 240 presentation frames and their complete parsed RPU metadata matched.
RPU binary bytes differ due to CRC/extension ordering; canonical parsed content
and frame order match. Profile 8.1 signaling, dimensions 3840x1608, 10-bit
BT.2020/PQ, aspect ratio, non-video inventory/dispositions, original audio and
subtitle packet bytes/timing, startup interleaving and full audio/video decode
passed. Sample chapters are omitted. This source did not advertise static HDR
metadata in the initial stream probe; this is not universal static-HDR coverage.

Published `The Acolyte S01E07 - NVIDIA Dolby Vision P8.1 - 10s Test.mkv` in
`C:\MuxMender-Plex` (23,401,333 bytes); Plex test library refreshed. User reported playback passed and confirmed Dolby Vision options were available.
This is device confirmation for this short sample, not full-file certification. Encoding took approximately four seconds
(~2.5x, rounded terminal timing). Video payload grew 229.6%, from 6,725,436 to
22,168,870 bytes; this is preservation feasibility, not a savings result.

The first attempt near 300s failed reference-timeline validation before encoding.
It is retained in `reports/dv81-20260905-215654-6fbd2f96`.
Raw HEVC muxing emitted generated-configuration/unset-timestamp warnings;
final reconstructed signaling, decoded timing and complete RPU checks passed.
Full-file NVIDIA preservation remains blocked pending broader validation.

## Existing AMD full-file workflow

An explicit `dv_full_file.py --experimental-nvidia` research option was added
after user approval of the initial DV sample. The normal `muxmender.py
--preserve-dolby-vision` gate remains AMD-only. NVIDIA uses the same p7/CQ18,
no-B-frame options as the reviewed sample, without scaling or tone mapping.

Before encoding, every source frame is decoded and checked for progressive
timing, RPU presence and unsupported extra dynamic HDR. Compact frame evidence
is compared incrementally, including static HDR values and timestamps. Original
non-video dispositions, aspect ratio and startup interleaving are also checked.
All original tracks/chapters, full parsed RPU content and order, and full audio/
video decode are verified before publication. The 2 GiB free-space stop remains;
an additional post-encode check reserves room for all remaining retained copies.
No original file is modified. Intermediate files are kept for recovery.

113 tests pass. A 30s sample and the full-file path on an 880-frame reference
passed. The full Acolyte episode is running in
`reports/nvidia-dv-full-episode/dv-full-20260905-220850-d5554477`.
Its final report must pass before a Plex output is published. This source's
decoded frames contain static HDR metadata even though the initial stream-only
probe did not advertise it. The smoke comparison preserved those values exactly.

Standalone command, dry run by default:

```powershell
python -u dv_full_file.py "Y:\TV\path\episode.mkv" --qp-i 21 --qp-p 23
```

Add `--execute` to run. Explicit `--ffmpeg`, `--ffprobe`, `--dovi-tool` and
`--work-dir` paths are supported. General optimizer defaults are unchanged.
This is AMD HEVC only, continuous constant-rate Profile 8.1 video starting at
zero. Unsupported profiles/timing fail closed. There is no CPU fallback.

Every run creates a unique directory with `terminal.log`, `status.json`, and
on completion/failure `validation.json`. Status is phase-level; the terminal
log contains within-stage progress. Compressed intermediate files are retained.
Nothing is deleted or overwritten. A `STOP` file inside the run directory
requests cancellation during stages; metadata probes have separate timeouts.
Stages have a four-hour cap; metadata packet probes have ten-minute caps.
No lossless full-resolution disk intermediate is generated.

Validation compares all video packet presentation timestamps, audio/subtitle
packet hashes and timings, chapters, dimensions/color tags, first-frame static
HDR (with reported one-unit chromaticity rounding tolerance), and full RPU
content/count/frame order. Large RPU JSON comparisons read one record at a
time. Extension-block ordering/CRC can change, as in the sample workflow.
A full output decode must pass. Source size/mtime is checked; no full source
file hash is claimed. Pixel-perfect/perceptually identical quality is not claimed.

Current muxing retains the experimental FFmpeg raw-stream timestamp/config
warnings; full timestamp and parsed DV metadata validation are required.
An accepted report is `verified-full-file-awaiting-playback`, not a claim of
final user approval or guaranteed space savings. Review total output size
and visual playback before using it as an optimization result. Only manually
publish the verified final video to the Plex test-output library; keep
intermediates outside that library.

2026-09-05 smoke result:
`reports/dv-full-20260905-104626-0a8dc134/validation.json` passed.
Full episode launched:
`reports/dv-full-20260905-104650-3893eee8/` (completion pending).

NVIDIA DV sample playback update: user confirmed "passed, I could see the dolby
vision options there." Recorded in the validation report, Plex manifest and
dashboard. Broader scene/source tests and full-file validation remain pending.

## Multi-audio verification correction

Full Acolyte verification exposed two container-level differences: physical
interleaving between separate audio tracks, and AAC packet-duration rounding
from 43ms to 42ms. Packet count, order within each track, presentation timestamps
and encoded payloads were unchanged. Source and output AAC decoded PCM SHA-256
matched exactly. Comparison now groups packets by track without sorting within
tracks. At most 1ms AAC duration rounding is allowed only with exact bytes/PTS/
sequence and an additional full decoded PCM hash comparison. Other duration
changes are rejected. This changes verification, not the audio or its timing.
115 tests pass, including negative cases for missing/reordered/changed packets.

The first full run and its failed strict comparison report are retained.
`python dv_full_file.py --verify-existing RUN_DIRECTORY` continues verification of that retained
NVIDIA output without re-encoding: current source bitstream identity, original
tracks/chapters, complete RPU content/order, every decoded frame/static HDR value,
and full output audio/video decode. A new report directory preserves provenance.

## Full NVIDIA episode result

Automated checks passed; full-episode TV playback review remains pending.

- Source: The Acolyte S01E07, 2502.542 seconds, Profile 8.1.
- Preserved 3840x1608, 10-bit BT.2020/PQ, sample aspect ratio and all 60,061
  decoded frame timestamps (2ms tolerance). Static HDR values matched exactly
  on every frame; RPU data was present throughout.
- Complete parsed RPU content, count and frame order matched. Only CRC and
  extension-block order are normalized in that comparison.
- Audio/subtitle encoded bytes, order within each track, presentation timestamps,
  track inventory/dispositions and chapters matched. 35,939 AAC packet-duration
  fields rounded from 43ms to 42ms. Complete decoded AAC PCM hashes matched;
  no audio retiming, re-encoding or offset was applied. EAC3 durations matched.
- Startup interleaving and complete audio/video decode passed.
- Source: 2,115,741,764 bytes. Output: 5,910,889,616 bytes (+179.38%). This is
  preservation feasibility, not a successful space-saving optimization.
- NVIDIA encoding: 850.06s (14m10s), 2.94x playback speed; verification additional.
- Source stat checks passed. A fresh source video extraction matched the audited
  source bitstream SHA-256. No full original-container hash is claimed.
- Plex: C:\MuxMender-Plex\The Acolyte S01E07 - NVIDIA Dolby Vision - Full Episode Verified.mkv

The first full-run report remains failed due to an overly strict cross-track/
AAC-duration comparison. This new independent report supersedes that result
without changing or re-encoding the media. Raw-HEVC mux configuration/timestamp
warnings remain documented; final reconstructed signaling and decoded timelines
passed validation. The normal optimizer's AMD-only preservation gate remains.
115 unit tests pass. No Git commands or source-media changes were made.
