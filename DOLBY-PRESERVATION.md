# Dolby Vision preservation experiment

`dv_preservation_test.py` is a standalone, AMD-only development experiment,
not a full-file optimizer. The general optimizer still skips unsupported DV
re-encoding. All original files remain read-only; no files are removed.

Example (dry run; add `--execute` to encode):

```powershell
python -u dv_preservation_test.py "Y:\TV\path\episode.mkv" --start 300 --seconds 30
```

Use `--ffmpeg`, `--ffprobe`, and `--dovi-tool` for explicit tool paths.
Experimental `--qp-i` / `--qp-p` controls allow compression comparisons while
keeping AMD's quality preset unchanged. Defaults remain 18/20; a 21/23 trial
requires explicit arguments. Higher QP trades fidelity for compression and
must pass fresh visual review, not only metadata checks.
The default dovi_tool path is the project-local 2.3.3 installation.
`--work-dir` defaults to `reports`, keeping intermediates outside Plex's
`test-output` library. Each run has a new directory, progress/status and a
validation report. Failures and intermediates are retained. No CPU fallback,
software installation, scaling, tone mapping, or profile conversion is automatic.

The input gate accepts only HEVC 10-bit, single-layer Profile 8.1 candidates.
The requested 1..30 seconds starts near `--start` at a preceding keyframe.
A padded reference is copied first, then the same presentation-frame range
is selected for encoding and RPU metadata. Duration is rounded to whole frames
(30 seconds at 24000/1001 fps becomes 719 frames, 29.988 seconds).
Other timeline configurations fail closed. Samples omit chapters
deliberately; full-episode chapter preservation is not implemented here.

Checks include exact frame count and presentation timeline, dimensions and
color tags, full video decode, audio/subtitle packet hashes and timestamps,
and Dolby Vision metadata for each frame. Full parsed RPU fields are compared
in frame order. FFmpeg can reorder extension blocks when writing the DV
configuration; block ordering and the resulting CRC are ignored, not metadata
values. Binary hashes and whether they match are reported separately.

AMD may round ST2086 chromaticities by one 1/50000 quantization unit. The
validator allows and reports that difference only; luminance/CLL changes or
larger coordinate changes fail. This is not a claim of lossless visual quality.

## 2026-09-05 results

The 30-second scene near five minutes passed the automated checks, user visual
review, and user confirmation of Dolby Vision picture mode on a Sony Android
TV. The actual sample is 719 frames / 29.988 seconds. See
`reports/dv81-20260905-092939-94e00a88/publication.json` for like-for-like
video-payload savings of 26.5056%. This supersedes the padded-reference size
calculation in that run's original validation report. Current code counts
only the selected frame range. This result is not a whole-file estimate.

The Plex library is configured as Other Videos. Browser playback on the PC
alone did not establish Dolby Vision display output; the Sony TV test did.
Further scenes and whole-file preservation remain to be tested.

Two additional 719-frame sections were tested on 2026-09-05. Both passed
automated checks, retaining DV metadata content/frame alignment and the
sample audio/subtitle packets. Near 12 minutes, video payload shrank 43.7%;
near 22 minutes it grew 25.5%. Both are in Plex test-output for visual review.
Results and terminal log: `reports/dv-scenes-20260905-101630-261332b0/`.
The variation confirms that the current quality settings do not guarantee
space savings; a full-file optimization has not been launched.

### Compression tuning

An explicit QP21/23 test of the same 22-minute scene passed automated checks
and reduced video payload by 46.2625% relative to its source frame range.
The final sample including audio/subtitles is 43,625,933 bytes. Plex filename:
`DV-Knight-22min-Tuned-QP21-23-dv81-20260905-103347-6eaa197d.mkv`.
Visual and Sony Dolby Vision playback review of this new quality setting is
pending. Previous approved samples are retained; default QP values are unchanged.
Report: `reports/dv-tuning-20260905-103347-d9be197a/dv81-20260905-103347-6eaa197d/validation.json`.

### Earlier opening-logo experiment

The selected A Knight of the Seven Kingdoms S01E02 Profile 8.1 source passed
the structural/content checks for a 192-frame (8.008-second) sample:
`reports/dv81-20260905-092313-ecd06135/validation.json`.
Dolby Vision playback and visual comparison are still pending. The sample
uses HEVC AMF Main10 with the `transparent` preset (CQP I=18/P=20); this
preset name is not a guarantee of transparency. The sample is larger than
its source segment and must NOT be accepted as a space-saving optimization.

Remaining: representative scenes beyond opening titles, rate/quality tuning,
bit-exact RPU packaging alternative, explicit timestamp generation without
muxer warnings, stronger source-to-reference stream verification, durable
terminal log capture, full-file support, and NVIDIA/Intel validation. The
installed GPU is the only hardware tested; profile 5/7 remain unsupported.

References:

- https://github.com/quietvoid/dovi_tool
- https://ffmpeg.org/ffmpeg-bitstream-filters.html#dovi_005frpu
