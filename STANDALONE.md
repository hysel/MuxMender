# Standalone usage and recovery

MuxMender is a Python command-line tool. VS Code and its extension are optional
development interfaces, not end-user requirements. Python 3.10+ and FFmpeg /
FFprobe are required. No installer or driver is run automatically.

## Live job dashboard

Run `python dashboard.py` and open http://127.0.0.1:8765 for progress, stage ETA,
history, results, and logs. New command-line jobs are recorded automatically.
No VS Code or extra packages required. See [DASHBOARD.md](DASHBOARD.md).

## Check your installation

```powershell
python muxmender.py --check-dependencies --hardware auto
# Also check the optional native Dolby Vision runtime without starting a GPU job:
python muxmender.py --check-dependencies --hardware amd --dolby-preview-backend d3d11
```

Use `--ffmpeg` and `--ffprobe` with executable paths if they are not on PATH.
The check reports executable versions, detected vendors and listed encoders.
An encoder being listed does not guarantee hardware compatibility. Missing
components are reported with setup guidance. Existing interactive requirement
prompts can open an official download page only when selected by the user;
the user performs installation and then repeats the check. Native helper
packaging/build instructions are in `native/muxmender-d3d11/README.md`.

## Analyze, then execute

### Opt-in Dolby Vision Profile 8.1 preservation

Single-file experimental route, currently validated only on AMD. Ordinary scans
still skip Dolby Vision by default. This route preserves resolution, copies
audio/subtitles/chapters, validates RPU content/order, and decodes the entire
result before acceptance. It does not guarantee identical visual quality.

```powershell
python muxmender.py "PATH\episode.mkv" --preserve-dolby-vision --dry-run
python muxmender.py "PATH\episode.mkv" --preserve-dolby-vision --execute --output-dir "E:\MuxMender-output"
```

Use `--dovi-tool PATH`, `--ffmpeg PATH`, and `--ffprobe PATH` when needed.
Missing tools offer an official download page, never automatic installation.
The tested default is AMD HEVC quality preset, QP I=21/P=23; explicit
`--dv-qp-i` and `--dv-qp-p` tune it. NVIDIA/Intel/CPU, resizing, AV1, batch
folders, preview ranges, other DV policies, and non-balanced `--quality` are
rejected in this route. Unsupported Dolby Vision profiles remain unchanged.

`--output-dir` here contains unique `dv-full-*` run folders with the result,
validation report, and retained intermediates; it is not a mirrored library.
Default location is the project's `reports` folder. Reserve at least four times
the source size plus 2 GiB. Nothing is automatically published to Plex or deleted.
`--min-savings` defaults to 5% **total-file** savings; smaller savings fail
acceptance but retain the output for inspection. Each stage uses the experimental
pipeline's four-hour timeout, not the generic hardware stall timeout. Progress
is recorded in the local dashboard. Playback review is still required.

```powershell
python -u muxmender.py 'Y:\TV Movies' --dry-run --report 'new-analysis.json'
python -u muxmender.py 'Y:\TV Movies' --execute --hardware auto --output-dir 'D:\Optimized' --report 'new-run.json'
```

File paths work instead of folders. Dry run remains the default. Reports must
have a new `.json` path; existing reports are never overwritten. Output mirrors
the folder structure. Exact dimensions are preserved unless a resize option is
explicitly requested. Dolby Vision is skipped by default. The explicit native
DV-to-PQ test remains limited to 1–10 seconds, not whole episodes or movies.

Terminal progress includes a text bar, elapsed time and an estimated remaining
time. `MUXMENDER_PROGRESS` lines remain for machine consumers. Estimates are
approximate; native multi-stage tests label stage progress separately.

## Failure and cancellation

- Ctrl+C stops the owned encoder process; original and partial media remain.
- GPU status messages without advancing media time do not reset the stall timer.
- CPU fallback asks for an explicit yes by default. `--hardware-fallback never`
  disables it; `--hardware-fallback cpu` explicitly authorizes it.
- Failed, cancelled and rejected partials are never deleted or reused. Retry
  creates a fresh partial; successful final outputs are never overwritten.
- General output publication uses hard links; on unsupported storage the
  completed partial remains available and the run reports an error. Recovery
  and final names share content—do not edit either in place.
- Recovery restarts the affected file; it does not resume an interrupted codec
  bitstream. Check retained files and free space before repeating large jobs.

The native diagnostic retains two lossless intermediates, which can be much
larger than the source. This is why its duration cap has not been lifted.
No original media is ever deleted, overwritten, moved or renamed by MuxMender.

## Experimental streaming HDR test

The separate streaming mode accepts a single DV profile 5 source and a bounded
1–60 second interval. It pipes native reconstructed FFV1/Matroska directly into
the HEVC encoder. The OS pipe provides backpressure; no lossless intermediate
is written to disk. Logs use a separate channel from binary video.

```powershell
python -u muxmender.py 'SOURCE.mkv' --streaming-delivery-test --dolby-preview-backend d3d11 --dolby-vision-policy hdr-preview --hardware amd --hardware-fallback never --preview-start 300 --preview-seconds 60 --output-dir test-output
# Dry run by default. Add --execute to generate a new test directory.
```

The native runtime must be rebuilt with `--stream-output` support. Color and
encoder preflights precede the media job. If either process fails or the pipe
stalls, both owned processes are stopped and partials retained. Successful
runs retain a compressed video-only intermediate, the final video with copied
audio/subtitles, and `validation.json`. These are separate compressed files.

Encoder failure can offer CPU fallback using the usual explicit fallback
policy; it restarts the interval in a fresh directory. Native color-stage or
ambiguous pipe-stall failures stop for diagnosis instead of silently retrying.

Validation checks frame counts and presentation timing against the original
interval, copied audio/subtitle packet hashes and timestamps, 10-bit PQ tags,
exact dimensions, and full output decoding. Savings measure compressed video
payload for that interval only. No per-run lossless quality reference is saved.
HDR PQ output is not Dolby Vision; viewing on the intended player remains
necessary. Nonzero source video start times are blocked until separately
validated. Full-file streaming is not enabled by this experimental option.

## Explicit full-file streaming

```powershell
python -u muxmender.py 'SOURCE.mkv' --full-file-streaming --dolby-preview-backend d3d11 --dolby-vision-policy hdr-preview --hardware amd --hardware-fallback never --output-dir 'D:\Optimized'
# Review the dry-run plan, then add --execute. No preview range options allowed.
```

This opt-in mode reads video to EOF and copies the original audio, subtitles,
attachments and chapters without preview trimming. Source video must start at
zero and duration must be known, positive, and at most 24 hours. Existing
profile-5-only and exact-dimension safeguards still apply. Dynamic Dolby Vision
metadata is intentionally replaced by reconstructed HDR PQ, not preserved.

Before execution, at least twice the source file size plus 2 GiB must be free
for two retained compressed files. Free space is checked during encoding and
copying, stopping below a 2 GiB reserve. The encoding watchdog defaults to at
most 12 hours (`--max-runtime-hours`), also bounded relative to media duration;
validation has separate timeouts. The stage watchdog detects lack of progress.

Each run has a new `stream-full-*` directory with `status.json` (phase, process
ID, progress and update time), the compressed intermediate, final
`episode-hevc.mkv`, and a final `validation.json`. Create a file named `STOP`
inside that particular run directory to stop encoding/copying/decode safely.
Packet-probe verification checks the stop request between probes, so a stop
may wait for the current probe. Ctrl+C also stops owned encoding processes.
No source or partial is deleted, and failed retries start in a new directory.

For a persistent log as well as terminal output, use `python -u run_logged.py`
with the same arguments. It creates a new log under `reports/` and requires no
VS Code. A long run is not successful until its final validation status says
`verified-full-file`; a playable partial or 100% encoding indicator alone is
not sufficient. Whole-episode validation and playback review are still required.
