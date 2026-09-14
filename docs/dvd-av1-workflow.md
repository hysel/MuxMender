# Standalone DVD AV1 workflow

Dry-run and hardware inventory (no encodes, no output directories created):

```powershell
muxmender-hardware
muxmender-dvd-av1 "Y:\TV\Series" --output-dir "E:\DVD-AV1"
```

Explicit runtime checks and encoding:

```powershell
muxmender-hardware --execute
muxmender-dvd-av1 "Y:\TV\Series" --output-dir "E:\DVD-AV1" --execute --accept-deinterlace
```

Without installation, use `python python/encoder_capabilities.py` and
`python python/dvd_av1_batch.py` with the same arguments. FFmpeg and ffprobe
must be on PATH, or provided via `--ffmpeg` and `--ffprobe`.

Hardware inventory distinguishes detected adapters, listed FFmpeg encoders,
and a successful four-frame runtime test. Tests run sequentially on the
backend's default adapter. They do not certify every adapter, bit depth,
resolution, setting, driver, or player. Standard CLI hardware execution now
also performs the synthetic preflight. Missing dependencies include official
download URLs; no automatic driver install or silent CPU fallback is added.

The DVD command is an opt-in experimental AMD AV1 QP80 workflow, restricted
to 720x480 MPEG-2, 8-bit, 8:9 SAR, top-field-first 29.97 fps DVD content.
`--accept-deinterlace` explicitly approves 59.94 progressive output; dimensions
and framing stay unchanged. Other formats, including existing HEVC/AV1 and
Dolby Vision, are skipped for separate review. No automatic source substitution.

All mapped audio/subtitle tracks are copied. Validation checks track metadata,
chapters, duration, every decoded frame's dimensions and pixel aspect ratio,
full video/audio decode, and audio/subtitle packet payload hashes. Known AMD AV1 crop padding is permitted only with
decoded evidence; clients still require playback review. This is not a
perceptual quality metric or universal playback guarantee.

Outputs mirror the input directory tree with `.AV1.mkv` names. Inputs and
outputs must be disjoint. Exclusive output creation, source hashes, publication
hashes, free-space guards and timeouts protect the workflow. There is no
delete-originals or overwrite option. Failed intermediates are retained for
diagnosis. Repeating the command resumes verified outputs only when source and
output hashes match their receipt; unverified existing outputs fail closed.
Dashboard jobs include overall file counts and current-stage progress.

The one-off series replacement scripts are not part of this CLI. Publishing
to a server and deleting its originals still requires a separately authorized
workflow; conversion alone never authorizes deletion.
