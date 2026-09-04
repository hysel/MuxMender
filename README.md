# MuxMender

MuxMender recursively analyzes a media library and creates a safe optimization plan. It can transcode inefficient video streams to HEVC or AV1 while preserving the original resolution and copying audio, subtitles, attachments, metadata, and chapters.

The default is a **dry run**. Originals are retained during normal execution and optimized files are written as sidecars such as `Movie.mp4.muxmender.mkv`.

## Requirements

- Python 3.10+
- FFmpeg and FFprobe available on `PATH`
- FFmpeg built with `libx265` for HEVC or `libsvtav1` for AV1

## Quick start

Analyze a library and show the proposed commands without changing anything:

```powershell
python muxmender.py "D:\Media"
```

Save a machine-readable report:

```powershell
python muxmender.py "D:\Media" --report analysis.json
```

Create HEVC/MKV sidecar files using the balanced quality profile:

```powershell
python muxmender.py "D:\Media" --execute
```

Use AV1 and mirror output into a separate directory:

```powershell
python muxmender.py "D:\Media" --codec av1 --quality balanced --output-dir "E:\Optimized" --execute
```

## Safety behavior

- Dry-run is the default; `--execute` is required to run FFmpeg.
- Existing outputs are skipped unless `--overwrite-output` is provided.
- Each encode is written to a hidden partial file and probed before being accepted.
- Video codec, resolution, duration, audio codecs, subtitle streams, and HDR/color signaling are checked.
- Outputs saving less than 5% are rejected by default; change this with `--min-savings`.
- Dolby Vision files are skipped because ordinary transcoding may discard dynamic metadata.
- Originals are never deleted during normal operation.
- Deletion requires both `--delete-originals` and the deliberately awkward confirmation `--confirm-delete DELETE_ORIGINALS`. It occurs only after the new file passes verification.

## Quality profiles

`balanced` is the default. `transparent` spends more space to reduce visible loss; `compact` prioritizes savings. These profiles are perceptual, not mathematically lossless. Always test representative files on your playback devices before processing a large library.

HEVC is selected by `--codec auto` because it has broader hardware decoding support than AV1. AV1 is opt-in and generally compresses better, but encodes more slowly and requires newer clients.

Efficient video that is already HEVC or AV1 is not needlessly re-encoded. If necessary, its streams are losslessly remuxed into MKV to provide a consistent container.

## Full options

```powershell
python muxmender.py --help
```

## Important limitations

- No lossy transcode can guarantee identical quality. MuxMender uses conservative constant-quality settings.
- HDR color tags are carried into the encode, but HDR10 static metadata preservation varies by FFmpeg build and input. Review HDR output before deleting a source.
- Dolby Vision requires a specialized workflow and is intentionally not automated.
- Copied lossless audio preserves quality and formats such as TrueHD/Atmos, but it also limits potential space savings.
