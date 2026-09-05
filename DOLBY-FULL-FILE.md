# Experimental full-file Profile 8.1 workflow

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
