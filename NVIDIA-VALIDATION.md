# NVIDIA generated-fixture validation — 2026-09-05

## Full SDR HEVC result (2026-09-05)

Full Commando (90m23s) passed independent automated verification after normal
standalone NVIDIA HEVC execution. Report directory:
`reports/nvidia-full-commando-20260905-204727-7a3ce153`.
The final `full-verification-*` report is `verified-full-file-playback-approved`.
User confirmed: "movie looks good, sound and video are in sync." The playback
device was not specified in that confirmation; no device matrix is claimed.

- All 130,020 decoded frames retained their timestamps within 2 ms; dimensions
  1920x1040, SAR, 8-bit pixel format, BT.709 color and range were preserved.
- Audio/subtitle packet bytes and timing, stream inventory/dispositions and
  chapters matched. Startup interleaving and full video/audio decode passed.
- Original: 9,262,466,043 bytes; output: 6,766,258,612 bytes; 26.95% smaller.
- Normal CLI encoding plus muxing: 575.16 seconds, 9.43x playback speed.
  Verification time is additional. No identical visual-quality claim.
- Plex: `C:\MuxMender-Plex\Commando (1985) - NVIDIA HEVC - Full Movie Verified.mkv`.
  Published as a hard link to the verified generated output; test library refreshed.
- Source size/mtime matched from capture during encoding through verification;
  no full original-file hash is claimed. Originals were not modified.

User playback review passed for this file; separate device coverage remains
unconfirmed. This validates the tested
SDR HEVC file's automated checks only, not all NVIDIA scenarios. Full HDR/AV1
validation remains separate; NVIDIA Dolby Vision preservation stays blocked.
Storage was available at restart (44.1 GiB); earlier storage-blocked notes below
are historical. The first single-thread diagnostic was stopped and retained;
the successful retry used automatic decoder threading. No Git commands run.

## Current integrated result ? 2026-09-05

NVIDIA HEVC/AV1 now uses a video-only encode followed by a stream-copy final
mux with original non-video tracks and a finite 10-second interleaving buffer.
The video stage preserves source timestamps/time base. A 2048-packet startup
check rejects unknown ordering or over 100ms of audio lead before video.
This is encoder-capability based; there is no RTX-model-specific branch.

All six generated fixtures and four real SDR/HDR10 samples passed in
`reports/nvidia-validation-20260905-195603-7925d098/REPORT.md`.
Final playback files are the four **Corrected v3** entries in `C:\MuxMender-Plex`.
Sample sizes/speeds are observations, not identical-quality claims or isolated
benchmarks. Test H was synchronized in Chrome with HEVC video copy; v3 device
review is still pending. NVIDIA Dolby Vision preservation remains blocked.

The five-minute two-stage stress run passed startup ordering, exact original
audio/subtitle packet signatures, dispositions, chapters, dimensions, aspect,
color/bit depth, frame count/timing (2ms tolerance), and full decode. Empty and
sparse subtitle tracks were retained. Peak Windows process working sets were
513,703,936 bytes for encoding and 45,252,608 bytes for finalization. These are
measured bounds for the tested workload, not a universal resource guarantee.

Normal standalone CLI execution also passed on the saved 31-second reference.
109 unit tests pass. Production preflight requires free space of twice the
source size plus 512 MiB for the two-stage path. Only about 2.2 GiB is free on
C:, so full-movie validation is blocked on storage and device playback review.
No source was moved/deleted, no Git commands run, and no software installed.

Historical results below predate the interleaving guard and are superseded.


## Update: standalone validation and dashboard

`python validate_nvidia.py "SDR-FILE" --hdr-source "PQ-FILE"` now runs generated
fixtures first, then separately saved samples, with automatic installed-tool
discovery and per-capability results. See STANDALONE.md for bounds and controls.

The combined run `reports/nvidia-validation-20260905-175901-0b2fe5b8/REPORT.md`
passed all ten automated tests on NVIDIA device 0 / driver 616.64 / FFmpeg 9.0.1.
It remains **awaiting playback review**, not full-file certification.

| Sample | Dimensions | Actual seconds | Output MB | Encode speed | Size change vs copied reference |
|---|---|---:|---:|---:|---:|
| Commando SDR HEVC | 1920×1040 | 31.155 | 39.87 | 8.06× | -29.70% |
| Commando SDR AV1 | 1920×1040 | 31.155 | 56.84 | 13.38× | +0.23% |
| American Sniper PQ HEVC | 3840×1600 | 32.490 | 32.03 | 3.00× | -53.78% |
| American Sniper PQ AV1 | 3840×1600 | 32.490 | 39.37 | 4.89× | -43.18% |

Keyframe-aligned references are slightly longer than the requested 30 seconds.
Real-sample checks passed exact dimensions, pixel format, color, static HDR
metadata where present, decoded progressive frames and presentation timing,
audio/subtitle packet bytes/timing, stream dispositions and full sample decode.
Original size/mtime and reference SHA-256 remained unchanged. This is not a
perceptual-quality or full-file savings claim. Dolby Vision stays blocked.

Retained failed HDR runs exposed automatic subtitle-default changes and an
overly strict unknown/progressive stream-tag comparison. The validator now sets
source dispositions explicitly and requires decoded progressive frames before
accepting an unspecified source field-order tag. Earlier failed reports remain
unchanged; the combined run is the current result.

The redesigned dashboard uses one stationary completed-work bar, textual stage
progress, capability results and searchable history. Unknown progress has no
bar. The served HTML/API, JavaScript parsing, DOM-model interactions and all 103
Python tests passed. Browser screenshot inspection was unavailable in this session.

No Git commands, installations, full-file conversions or source-media mutations
were performed. The earlier fixture-only findings below remain historical evidence.

Six corrected generated-fixture tests passed. No real media was opened. No Git
commands, installations, driver changes, source-media operations, or VS Code
window operations were performed.

Local `.git/HEAD` and branch-ref file reads identify `testing/nvidia-validation`
at `fc7fddad4f33a271272d48cacf6e182ad16e90c9`. This is not a Git working-tree
cleanliness check. The five requested project instruction documents were read.

## Environment and method

- Python 3.13.15; FFmpeg and FFprobe 9.0.1 Gyan full build.
- NVIDIA device 0: GeForce RTX 5050, driver 616.64, reported memory 8151 MiB.
- FFmpeg was absent from this shell's PATH. The existing WinGet installation
  required approved execution outside the sandbox; nothing was installed.
- HEVC, AV1 and H.264 NVENC are listed. HEVC/AV1 were actually tested; H.264 was
  not. AMF/QSV and software encoders are also listed, not hardware-validated here.
- `validate_nvidia.py` includes the standard-library generated test runner. It uses
  the existing MuxMender encoder selection and command builder, and registers
  its progress/log with `job_tracking`. Product encoding and DV gates are unchanged.
- Each fixture is two seconds / 48 frames at 24 fps, with generated PCM audio,
  SubRip subtitles and one chapter. Sources use lossless x265; tested outputs
  use NVENC balanced settings: p6, HQ, VBR CQ21, bitrate 0, GPU index 0.
- Generated PQ patterns test 10-bit handling and color signaling. They are not
  calibrated HDR scenes and contain no mastering-display, MaxCLL or Dolby Vision
  metadata. CPU fixture generation is deliberate, not an NVENC fallback.

## Corrected results

Sizes are decimal MB for complete containers, including copied audio/subtitles.
Speed is two seconds divided by encoder-process wall time, including startup,
source decoding and muxing; it excludes fixture generation and validation.

| Fixture | Codec | Source MB | Output MB | Speed |
|---|---|---:|---:|---:|
| 1920×1080, 8-bit BT.709 | HEVC | 6.55 | 2.83 | 3.75× |
| 1920×1080, 8-bit BT.709 | AV1 | 6.55 | 3.32 | 4.98× |
| 1920×1080, 10-bit BT.2020/PQ | HEVC | 9.40 | 2.86 | 3.81× |
| 1920×1080, 10-bit BT.2020/PQ | AV1 | 9.40 | 3.29 | 4.28× |
| 3840×2160, 10-bit BT.2020/PQ | HEVC | 34.96 | 6.86 | 1.36× |
| 3840×2160, 10-bit BT.2020/PQ | AV1 | 34.96 | 12.61 | 1.77× |

All six passed exact dimensions, pixel format/bit depth, primaries, transfer,
matrix and range checks. Audio/subtitle codec inventories, packet SHA-256 hashes,
PTS and durations match. Chapters, 48 video packets and presentation timestamps
match. Every output fully decoded in software with `-xerror -err_detect explode`.
Generated sources remained unchanged by full-file SHA-256 comparison.

These sizes compare lossy outputs against synthetic lossless sources. They do
not predict savings on existing compressed media or establish identical visual
quality. The brief speed measurements are not sustained-throughput benchmarks.
Hardware decoding, other GPUs, multiple-GPU selection, cancellation/failure
scenarios, static HDR metadata and Dolby Vision remain outside this validation.

## Retained evidence and monitoring

Authoritative corrected report:
`reports/nvidia-fixtures-20260905-154859-749c418b/validation.json`.
The same folder retains all fixtures, outputs, per-stage FFmpeg logs and output
packet/stream probes. Tracked terminal log:
`reports/job-20260905-154859-89a05b7d/terminal.log`.

The local read-only dashboard at http://127.0.0.1:8765 was started and its API
verified to show this completed job and log. Restart with `python dashboard.py`
if its server is no longer running.

Two earlier runs are retained for diagnosis:

- `nvidia-fixtures-20260905-154723-bda2ba75`: successful NVENC/decode smoke tests,
  but **not valid PQ/primaries validation**. Source primaries/transfer were absent,
  and the initial equality checks accepted absent values on both sides. Its
  `passed` result is superseded by the corrected report above.
- `nvidia-fixtures-20260905-154836-17f02ce0`: the stricter fixture check correctly
  failed on missing color tags. Explicit frame-level `setparams` fixed fixture
  signaling; the runner now requires all expected tags before testing encoders.

## Next boundary

Detection contains no RTX 5050 model dependency. The production selector still
uses detected vendors plus advertised encoders; this new runner validates actual
capabilities on device 0. It does not add general per-device production preflights
or establish support on other models.

The AMD-only Profile 8.1 Dolby Vision preservation gate remains unchanged.
NVIDIA Dolby Vision preservation is **not validated**. The user's prior AMD
full-episode result (53.7% savings, Sony Android TV playback and DV-mode approval)
is user-reported prior evidence and was not rechecked on this machine.

Before real-media work, obtain a path from the user, inspect it read-only, and
start with a short separately saved sample. Do not launch a full conversion or
bypass Dolby Vision gates.
