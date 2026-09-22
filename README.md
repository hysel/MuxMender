# MuxMender

**MuxMender's goal is to save disk space by re-encoding previously ripped or
otherwise lawfully obtained video files that you are authorized to process.**
It works on an existing media library—not on finding, downloading, or sharing
movies and television shows.

MuxMender recursively analyzes media, tests HEVC/H.265 and AV1 candidates, and
aims to produce smaller files while meeting the selected quality and preservation
checks. Original resolution is preserved by default; audio, subtitles, attachments
and chapters are copied where supported and checked. If no tested candidate meets
the requirements, the original is retained. Lossy re-encoding cannot guarantee
identical visual quality, and not every video benefits from another encode.

## Responsible use — no piracy

**This project does not support, promote, or facilitate piracy.** Use it only
with media you have the rights or permission to process. Do not use MuxMender
to obtain, distribute, or share unauthorized copies. It is a media optimization
project, not a content-download service or a DRM-circumvention tool.

## Tested formats and qualification status

“Validated” below means project testing of the stated route—not certification
by a codec vendor, a guarantee for every file, or universal player compatibility.
Container, video codec, HDR format, GPU/driver and playback device are separate
factors. Each new file still goes through its applicable checks. Research results
do not mean that a route is enabled in the deployed app.

| Format / route | Evidence and current scope |
| --- | --- |
| MKV and MP4 with H.264/AVC → HEVC in MKV | Full-file shared-workflow copies validated on NVIDIA, including MP4 input. See the [research results](docs/animation-research-status-20260921.md). |
| 1080p SDR H.264 → AV1 in MKV | AMD full-file and Chrome/Sony Plex playback tests completed for selected material. The [legacy AMD batch route](docs/AMD-AV1-BATCH.md) has its own narrower constraints; it is not blanket AMD qualification. |
| Previously ripped DVD MPEG-2 → AV1 in MKV | Tested AMD route for 720×480, 8-bit, 8:9 pixel aspect ratio, top-field-first 29.97 fps sources. Explicit deinterlacing approval produces 59.94 progressive output. See [DVD AV1 workflow](docs/dvd-av1-workflow.md). Not certification for every DVD format. |
| Legacy MPEG-4 Part 2 in AVI → HEVC/AV1 in MKV | Source timing/color recovery tested. One full repaired AV1 test copy passed validation and user playback; its damaged source audio required a separately approved repair. Other candidates missed size or quality targets. Not unrestricted AVI qualification. |
| 10-bit 4:4:4 H.264 input | Three-scene tests passed on four selected sources; full-file qualification remains pending. |
| 4K PQ/HDR10 HEVC → HEVC in MKV | Selected full-file validation passed, including native HDR preservation. A smaller candidate can still be rejected for quality. No fixed 16:9 resolution requirement. |
| Dolby Vision Profile 8.1 | Experimental preservation tests passed. Broader three-scene testing rejected the ordinary-DV candidate's quality/size settings; it is **not approved for automatic conversion**. |
| Combined Dolby Vision Profile 8.1 + HDR10+ | Selected NVIDIA full-file preservation and three-scene quality tests passed. **Research-only; automatic app routing remains disabled pending integration.** This does not certify all HDR10+ inputs or Dolby Vision profiles. |

HLG, other Dolby Vision profiles, additional pixel formats and other container/
hardware combinations are **not broadly certified** by this list. Recognition
by the scanner or support advertised by FFmpeg is not sufficient evidence.
Audio/subtitle copy validation likewise does not guarantee that every player can
direct-play the copied tracks.

Hardware qualification is also specific: the [Quadro P4000 tests](docs/p4000-qualification-20260920.md)
verified generated HEVC clips, not real-library HDR/DV quality. Do not infer that
all NVIDIA, AMD or Intel generations support the same codecs or settings.

## Choose a workflow

The [web UI and queue](docs/WEBUI.md) use shared analysis, encoding and validation
services. Safe-copy mode retains originals. **Replacement is a separate, explicit
choice that permanently removes originals only after successful validation and
verified publication.** Do not select replacement if you want to keep originals.

The standalone `python/muxmender.py` examples below describe the general CLI,
not every queue or experimental workflow. Its default is a **dry run**; normal
execution retains originals and writes sidecars such as `Movie.mp4.muxmender.mkv`.
The optional [DVD AV1 command](docs/dvd-av1-workflow.md) processes existing ripped
files and defaults to read-only inspection; it never deletes originals.

## Requirements

- Python 3.10+
- FFmpeg and FFprobe available on `PATH`
- FFmpeg built with `libx265` for HEVC or `libsvtav1` for AV1

## Quick start

Analyze a library and show the proposed commands without changing anything:

```powershell
python python/muxmender.py "D:\Media"
```

Save a machine-readable report:

```powershell
python python/muxmender.py "D:\Media" --report analysis.json
```

Create HEVC/MKV sidecar files using the balanced quality profile:

```powershell
python python/muxmender.py "D:\Media" --execute
```

Use AV1 and mirror output into a separate directory:

```powershell
python python/muxmender.py "D:\Media" --codec av1 --quality balanced --output-dir "E:\Optimized" --execute
```

## General CLI safety behavior

For the separately validated, experimental **AMD 1080p SDR AV1 batch route**, see
[safe sequential batches](docs/AMD-AV1-BATCH.md). It uses a disjoint output folder,
per-file integrity checks, bounded execution and checksum-verified repeat-run
skipping. It never publishes or deletes originals and does not change the general
optimizer's defaults.

- Dry-run is the default; `--execute` is required to run FFmpeg.
- Existing outputs are always skipped. Deletion and overwrite flags are rejected.
- Each encode uses a unique hidden partial file and is probed before acceptance. Failed/rejected attempts are retained; CPU retries use another new file.
- Video codec, resolution, duration, audio codecs, subtitle streams, and HDR/color signaling are checked.
- Outputs saving less than 5% are rejected by default; change this with `--min-savings`.
- Dolby Vision files are skipped because ordinary transcoding may discard dynamic metadata.
- This general CLI never deletes originals. Its former original-deletion confirmation flag is not supported. The separate queue's explicitly authorized replacement mode is described above.
- Accepted general-conversion outputs are published using an atomic no-overwrite hard link. The recovery name is retained and shares the same disk data, not a second copy. Filesystems without hard-link support fail safely and retain the completed partial.

## General CLI quality profiles

`balanced` is the default. `transparent` spends more space to reduce visible loss; `compact` prioritizes savings. These profiles are perceptual, not mathematically lossless. Always test representative files on your playback devices before processing a large library.

HEVC is selected by `--codec auto` because it has broader hardware decoding support than AV1. AV1 is opt-in and generally compresses better, but encodes more slowly and requires newer clients.

Efficient video that is already HEVC or AV1 is not needlessly re-encoded. If necessary, its streams are losslessly remuxed into MKV to provide a consistent container.

## Full options

```powershell
python python/muxmender.py --help
```

## General CLI limitations

- No lossy transcode can guarantee identical quality. MuxMender uses conservative constant-quality settings.
- HDR color tags are carried into the encode, but HDR10 static metadata preservation varies by FFmpeg build and input. Review HDR output and retain the source.
- Dolby Vision requires a specialized workflow and is intentionally not automated.
- Copied lossless audio preserves quality and formats such as TrueHD/Atmos, but it also limits potential space savings.

## Repository layout

Documentation uses neutral test-case labels instead of real movie, series or
episode titles. Media paths and title-bearing report paths in examples are
anonymized placeholders; substitute your own paths. Recorded technical findings
are unchanged. Actual media and runtime reports are not renamed by this convention.

- `python/`: standalone Python commands and shared logic.
- `python/ui/`: shared control-room and workflow design (HTML/CSS/JavaScript).
- `powershell/`: Windows setup and optional integration helpers.
- `docs/`: usage, hardware validation and handoff documentation.
- `tests/`: regression tests; run `python -m unittest discover` from the repository root.
- `native/` and `vscode-extension/`: optional integrations.

Start with [standalone usage](docs/STANDALONE.md), [local workflow](docs/WEBUI.md),
or the [NVIDIA handoff](docs/NVIDIA-HANDOFF.md). All commands run from the repository root.
