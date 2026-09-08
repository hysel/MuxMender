# Standalone usage and recovery

## Consolidated entry points

- `python python/muxmender.py`: analysis and optimization, including clean output names
  and optional video-only folders.
- `python python/validate_nvidia.py`: generated hardware tests and optional real samples.
- `python python/validate_nvidia.py verify-full SOURCE RUN --job JOB`: retained ordinary
  SDR HEVC/AV1 full-file verification; no encoding or source changes.
  Reads the normal CLI report and verifies additive playback track mapping when used.
- `python python/dv_full_file.py --verify-existing RUN`: retained experimental DV
  verification. The same script owns experimental full-file DV execution.
- `python python/staged_mux_stress.py --ordered-dv`: self-contained sparse/empty-track
  mux regression. This generated SDR fixture tests mux behavior, not DV metadata.
- `python python/dashboard.py`: the approved control room. `python python/webui.py` provides
  the library workflow and uses the same control room at `/history`.

Shared mux ordering and size acceptance now live in `mux_integrity.py`.
The former `nvidia_mux.py`, `optimization_acceptance.py`, `nvidia_validation.py`,
`verify_nvidia_full_file.py`, and `verify_dv_existing.py` entry points were folded
into the modules above. Update external scripts to the documented commands.

MuxMender is a Python command-line tool. VS Code and its extension are optional
development interfaces, not end-user requirements. Python 3.10+ and FFmpeg /
FFprobe are required. No installer or driver is run automatically.

## Live job dashboard

For the interactive local workflow (scan, approve previews/full episodes, queue,
cancel, and review results), run `python python/webui.py` and open http://127.0.0.1:8766.
See [WEBUI.md](WEBUI.md) for safety boundaries and setup instructions.

Run `python python/dashboard.py` and open http://127.0.0.1:8765 for progress, stage ETA,
history, results, and logs. New command-line jobs are recorded automatically.
No VS Code or extra packages required. See [DASHBOARD.md](DASHBOARD.md).

## Check your installation

### One-command NVIDIA validation

```powershell
python python/validate_nvidia.py
# Add an optional SDR sample; the original file is only read:
python python/validate_nvidia.py "Y:\path\movie.mkv"
# Include a separate non-Dolby-Vision PQ sample:
python python/validate_nvidia.py "Y:\path\sdr.mkv" --hdr-source "Y:\path\hdr.mkv"
```

No installation is required beyond existing Python and FFmpeg/FFprobe. Tools
are resolved from PATH or a single installed WinGet FFmpeg directory; ambiguous
locations require `--ffmpeg PATH --ffprobe PATH`. The installed-package command
is `muxmender-validate-nvidia` (installation is not required for script usage).

Generated HEVC/AV1 tests run first on `--gpu 0` (select another index explicitly).
Real samples run only if those tests pass. Default samples seek near 300 seconds
and request 30 seconds; `--start` and `--seconds` allow 1–60-second tests. A
keyframe-aligned copied reference can be slightly longer (at most 15 seconds).
The report gives its actual duration. No full-file conversion is available here.

Each invocation creates a unique `reports/nvidia-validation-*` folder containing
`REPORT.md`, `validation.json`, fixtures, copied references, encoded samples and
stage logs. No media is overwritten or cleaned up. Put a `STOP` file in that run
folder, or use Ctrl+C, to cancel. Free-space reserve and process timeouts apply.

Checks include exact dimensions, progressive frame timing, bit depth/color tags,
audio/subtitle packet hashes and timing, stream selection flags, attachments,
reference chapters, static HDR metadata on decoded frames, and full sample
decoding. The copied reference packets are checked against a bounded source
interval. Original checks use size/mtime; reference files use SHA-256.
Unknown color, interlaced video and dynamic HDR need separate validation.
Dolby Vision remains blocked; no AMD preservation gate is bypassed.

Results say Passed / Failed / Not tested for each capability. A passed sample
still awaits user playback review, and applies only to the recorded GPU, driver
and FFmpeg build. It does not certify full-file reliability, hardware decoding,
identical visual quality, or savings on other media.

```powershell
python python/muxmender.py --check-dependencies --hardware auto
# Also check the optional native Dolby Vision runtime without starting a GPU job:
python python/muxmender.py --check-dependencies --hardware amd --dolby-preview-backend d3d11
```

Use `--ffmpeg` and `--ffprobe` with executable paths if they are not on PATH.
The check reports executable versions, detected vendors and listed encoders.
An encoder being listed does not guarantee hardware compatibility. Missing
components are reported with setup guidance. Existing interactive requirement
prompts can open an official download page only when selected by the user;
the user performs installation and then repeats the check. Native helper
packaging/build instructions are in `native/muxmender-d3d11/README.md`.

## Analyze, then execute

HEVC/AV1 sources normally remain unchanged when another encode is unlikely to
help. Explicit `--reencode-efficient` requests another encode with the selected
codec and quality, subject to the normal minimum savings and preservation checks.
It does not override Dolby Vision or AV1 HDR safety gates. Review a short sample
before a full run; no quality equivalence is promised. Full verification has an
explicit `verify-full --hdr` mode for HEVC HDR10 only, using exact per-frame static
HDR metadata checks; AV1 HDR and Dolby Vision full-file validation stay separate.

New generated outputs preserve the complete source release basename for external
subtitle matching; only the container extension becomes `.mkv`. Encoding labels
in that name describe the source release, not necessarily the output codec.
The optional existing-file rename preview remains a separate explicit action.
No online identity lookup is performed. Review planned
names in a dry run; ambiguous input names may need manual correction. Without
an output directory, files go in a separate `MuxMender` subfolder beside the
source. Existing destinations are never overwritten. Existing media is not
renamed automatically. Experimental diagnostic intermediate names remain distinct.

Matching JPG/JPEG/PNG/WebP artwork is copied beside accepted full outputs using
the clean video basename, including recognized `-poster`, `-fanart`, `-banner`,
and `-thumb` suffixes. Source artwork remains unchanged; existing destination
artwork is preserved. Copy results or failures appear in the JSON report.

Use `--video-only-folder` to publish only video files, with no artwork or external
subtitle sidecars from the source folder or any subdirectory. Embedded audio and
subtitles remain preserved. No source files or existing destination extras are
deleted; use a fresh output folder for a video-only result. Standard conversions
retain intermediates separately under a sibling `.MuxMender-work` folder. The
experimental full-file DV script places the output in its run's `media` subfolder,
separate from diagnostic files. The option is disabled by default.

Example: `python python/muxmender.py "PATH" --execute --output-dir "D:\Optimized" --video-only-folder`

External subtitle timing depends on the cut and presentation timeline, not
video bitrate. NVIDIA full-file output preserves presentation timing; validated
Commando frames matched within 2 ms, with original embedded subtitle packets
unchanged. External subtitles must be for the same cut. To auto-load after clean
naming, use a matching basename (for example `Commando (1985).en.srt`); sidecar
subtitle files are not automatically renamed or copied by the current pipeline.

Optional missing-metadata enrichment for Plex and generated-file tags is planned
in TODO.md. It is not implemented or enabled by the clean-name feature.

Completed optimization runs print aggregate size reduction in decimal MB, GB,
TB, and percent. JSON reports include `savings_summary` with exact byte totals.
Only accepted outputs count; the percentage uses their combined original size,
not an average of file percentages. Retained originals and intermediates still
occupy storage, so this is not a measurement of disk space reclaimed.

Ordinary transcodes now perform a read-only preflight, including dry runs.
Unspecified color primaries/transfer/matrix/range produce `needs-review` before
creating media output. Otherwise, up to 256 video packets at the start, middle,
and near the end are checked for missing/nonfinite PTS/DTS and non-increasing
DTS. Reordered PTS from B-frames are allowed. This is a conservative sampled
check, not full-file timing or color validation. A review block returns exit
code 1 and records the reason in `--report`; other files can still be processed.
Remux/copy and specialized Dolby Vision workflows keep their separate rules.

### Opt-in Dolby Vision Profile 8.1 preservation

Single-file experimental route, currently validated only on AMD. Ordinary scans
still skip Dolby Vision by default. This route preserves resolution, copies
audio/subtitles/chapters, validates RPU content/order, and decodes the entire
result before acceptance. It does not guarantee identical visual quality.

```powershell
python python/muxmender.py "PATH\episode.mkv" --preserve-dolby-vision --dry-run
python python/muxmender.py "PATH\episode.mkv" --preserve-dolby-vision --execute --output-dir "E:\MuxMender-output"
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
python -u python/muxmender.py 'Y:\TV Movies' --dry-run --report 'new-analysis.json'
python -u python/muxmender.py 'Y:\TV Movies' --execute --hardware auto --output-dir 'D:\Optimized' --report 'new-run.json'
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
python -u python/muxmender.py 'SOURCE.mkv' --streaming-delivery-test --dolby-preview-backend d3d11 --dolby-vision-policy hdr-preview --hardware amd --hardware-fallback never --preview-start 300 --preview-seconds 60 --output-dir test-output
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
python -u python/muxmender.py 'SOURCE.mkv' --full-file-streaming --dolby-preview-backend d3d11 --dolby-vision-policy hdr-preview --hardware amd --hardware-fallback never --output-dir 'D:\Optimized'
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

For a persistent log as well as terminal output, use `python -u python/run_logged.py`
with the same arguments. It creates a new log under `reports/` and requires no
VS Code. A long run is not successful until its final validation status says
`verified-full-file`; a playable partial or 100% encoding indicator alone is
not sufficient. Whole-episode validation and playback review are still required.


## NVIDIA output finalization

HEVC/AV1 NVENC and Intel QSV execution encode one video-only MKV intermediate, then
stream-copies that video together with the original audio, subtitles,
attachments/data, metadata, dispositions and chapters into the final MKV.
There is no second video encode. Original dimensions, sample aspect ratio,
color and bit depth remain the defaults; video timestamps use passthrough.

This separates video encoding from final track interleaving. The final mux
uses ordered packet interleaving (`-max_interleave_delta 0`) so long subtitle gaps
do not flush video ahead of audio. A polling memory guard stops the owned mux
process above 1 GiB measured resident/committed high-water usage on Windows
(resident high-water on Linux). If measurement is unavailable, it fails closed.
This is a monitored stop threshold, not an OS-enforced allocation ceiling.
A bounded startup probe checks the first 2048 packets before publication;
unknown ordering or over 100ms of audio lead before the first video packet
rejects the output and retains recovery files. Normal staged/playback outputs
also require aligned audio/video at sampled seeks before publication. This is a conservative
compatibility check, not a substitute for decode and device playback tests.

Allow disk space for both the compressed video intermediate and final output.
The intermediate is retained for recovery; no original media is removed.
The dashboard shows encoding and finalization as separate phases. This flow
applies to detected HEVC/AV1 NVENC encoders, without a GPU-model lookup.
Opt-in Dolby Vision preservation supports AMD/Intel Profile 8.1; unsupported profiles remain blocked.

The video encoder also uses the demuxer time base to avoid clock rounding
drift on long/VFR timelines. Before normal NVIDIA execution, allow at least
twice the source file size plus 512 MiB free on the output volume; this is a
conservative preflight estimate, not a guarantee for every codec/quality.

## Optimization acceptance

Transcodes must shrink the complete file (default minimum 5%). Larger/equal
outputs are rejected even at a zero threshold. Quality is not automatically
lowered to force a saving. Experimental full NVIDIA DV runs first test a
bounded 30s sample and skip the full encode if that sample does not shrink.
The current full Acolyte result is rejected: larger and failed Sony TV playback.
See DOLBY-FULL-FILE.md for the remaining validation limits.

## Consolidated source layout

- `python/ui/`: all dashboard and workflow HTML, CSS and JavaScript, shared in one module.
- `python/dashboard.py` and `python/webui.py`: standalone HTTP servers and their backend logic.
- `mux_integrity.py`: shared mux, savings, audio rounding and media preflight checks.
- `validate_nvidia.py`: generated fixtures and retained ordinary-output verification.
- `dv_full_file.py`: full-file DV processing, retained verification and packet/frame checks.
- `tests/`: regression tests, including the dashboard DOM checks.

Keep design changes inside `python/ui/`; preserve the approved control-room layout and
stationary progress behavior. Avoid adding one-off scripts for shared logic.

Python commands now live under `python/`, Windows helpers under `powershell/`,
and project guides under `docs/`. Run commands from the repository root;
reports, portable tools and native runtime paths still resolve there.
Run the regression suite with `python -m unittest discover -q`.


## Optional playback defaults

Use `--compatibility-audio eac3` with the ordinary standalone command to retain
all original tracks and put default EAC3 first among audio tracks (new audio: 48 kHz, 640 kbps, lossy). A selected
existing EAC3 track is reused. Choose the source audio with
`--compatibility-audio-track N` (zero-based); absent a choice, use the unique
default audio or sole audio track. Ambiguous choices and unsupported channel
layouts stop for review; no automatic downmix. Known mono, stereo and 5.1 layouts
are accepted. This is an explicit playback preference, not GPU/model detection.

`--default-subtitle-track N` selects a zero-based embedded subtitle default while
retaining every subtitle and its forced flag. Omit it to retain subtitle defaults.
Both track options require `--compatibility-audio eac3`. Plex saved language/track
preferences can override file defaults; this does not repair Plex transcoder bugs
or guarantee every client can play EAC3/AV1. FFmpeg disposition semantics:
https://ffmpeg.org/ffmpeg.html#Stream-selection

Example (dry-run until `--execute` is added):

```powershell
python python/muxmender.py "D:\Media\Movie.mkv" --hardware intel --codec av1 --compatibility-audio eac3 --default-subtitle-track 0 --output-dir "D:\Prepared"
```

Video is not encoded a second time to prepare playback. The final copy verifies
original packet bytes/timestamps, stream metadata, chapters and requested flags,
then decodes all video/audio and checks startup interleaving. Added audio counts
against the savings threshold for video conversions. Explicit compatibility-only
remux of an already efficient video can grow the file; it is playback preparation,
not space savings. All sources/intermediates remain separate and retained.
Experimental Dolby delivery modes reject this option; DV gates are unchanged.
Jobs and verification stages appear in the terminal and control room dashboard.


## Optional existing-file rename mode

Rename is separate from conversion and requires an explicitly reviewed plan.
Preview never renames media and needs no FFmpeg, GPU or online service:

```powershell
python python/muxmender.py "C:\Media" --rename-plan "C:\Plans\rename.json"
```

The plan file must be new and its parent directory must exist. Entries show exact
source/destination paths, identity evidence and ready/unchanged/needs-review/blocked
status. A single-video folder containing a title and year can resolve abbreviated
filenames, e.g. `War Horse (2011)/s7-war.horse.1080.mkv` becomes
`War Horse (2011) - s7-war.horse.1080.mkv`. Uncertain abbreviated release names
are retained whole so release identifiers are not guessed away.
This is a folder-based proposal, not verified online movie
identification. Missing/conflicting years or ambiguous names require review.
Episode identifiers are retained. File extensions are preserved, so renaming an
MP4 never falsely labels it MKV. No video conversion occurs.

Rename proposals clean the title while preserving the original release tail,
including its punctuation and release group. For example,
`X2.2003.BluRay.720p.x264.DTS-WiKi.mkv` becomes
`X2 (2003) - BluRay.720p.x264.DTS-WiKi.mkv`.
Plans expose `release_suffix` for review. Conversion itself preserves the entire
source basename. These names retain source-release labels even if conversion
changes the actual codec. Rebuild older rename plans before applying them;
previously saved plans still contain their original proposed destinations.

For an ambiguous single file, provide its confirmed identity when creating a
new preview:

```powershell
python python/muxmender.py "C:\Media\s7-war.horse.1080.mkv" --rename-title "War Horse (2011)" --rename-plan "C:\Plans\war-horse.json"
```

Add `--rename-sidecars` to include same-basename subtitle and artwork companions,
including language suffixes such as `.en.srt`. Other names and subtitle
subdirectories remain untouched; inspect these associations before approval.
Folder names never change. Without that option, only videos are proposed.

After reviewing every ready entry, explicit apply is:

```powershell
python python/muxmender.py --apply-rename-plan "C:\Plans\rename.json" --execute --confirm-rename RENAME
```

Only ready entries are applied. Validation of the whole ready set happens before
renaming: source size/mtime/file identity must match the preview, destinations
must be unoccupied in the same directory, and no symlinks/junctions are followed.
Nothing is overwritten. A per-action JSONL journal is saved beside the plan;
if a filesystem error occurs mid-run, earlier renames remain and the journal
identifies completed/pending actions. Rebuild a preview before retrying; this is
not a transactional batch rollback. On systems without exclusive rename semantics,
exclusive hard-link creation followed by unlinking the old name is used; unsupported
filesystems fail instead of falling back to an overwrite. Media contents and
last-modified timestamps are preserved. No renames on Drive Y were performed during
development; all apply tests used disposable local fixtures.


Run the reusable hardware/mux regression without source media:

```powershell
python python/staged_mux_stress.py --hardware intel --codec hevc --playback-defaults
python python/staged_mux_stress.py --hardware intel --codec av1 --playback-defaults
```

Both run generated 60/300-second fixtures with explicit BT.709 color, sparse and
empty subtitles, retained original audio plus compatibility audio, timestamp/
packet checks, full decode, seeks and measured stage memory. No extra scripts
or software installation are required. Native NVIDIA remains the default vendor
for backward compatibility; `--ordered-dv` is a mux-only diagnostic, not DV approval.

### Integrated Intel HDR and Dolby Vision

After the full AV1 HDR10 and HEVC Profile 8.1 outputs passed automated checks and
Chrome/Sony TV playback, the normal standalone command now dispatches to those
same audited pipelines. No extra scripts are needed:

```powershell
python python/muxmender.py "C:\Media\movie.mkv" --codec av1 --hardware intel --quality transparent --reencode-efficient --output-dir "C:\Converted" --execute
python python/muxmender.py "C:\Media\episode.mkv" --preserve-dolby-vision --hardware intel --output-dir "C:\Converted" --execute
```

Omit `--execute` for a dry run. AV1 HDR requires unchanged resolution and original
tracks; compatibility-audio preparation, overwrite and CPU fallback are blocked
for this route. Quality and minimum savings follow the requested CLI settings;
transparent was used for the approved full-file test. All HDR frames are audited,
the known Intel MDCV clamp is repaired, and full independent frame/track/HDR/seek/
decode verification must pass before the final file is published. Recovery files
remain under `.MuxMender-work` and are excluded from subsequent media scans.

Dolby Vision remains opt-in and Profile 8.1 only. `--hardware auto` prefers an
available AMD GPU, then Intel; explicit Intel uses the tested QSV settings and
savings preflight. NVIDIA remains available through the separate research command.
No default DV conversion, resizing, source deletion or automatic installation was
enabled. Actual encoder operation and per-file preservation still must pass.

### Explicit Intel HDR/DV research


The separate research entry points remain available for diagnostics; integrated use is described above. The following
standalone commands write only to new, separate research directories:

```powershell
python python/validate_nvidia.py av1-hdr-research "C:\Media\movie.mkv" --run "C:\Tests\av1-hdr" --execute
python python/validate_nvidia.py verify-full "C:\Media\movie.mkv" "C:\Tests\av1-hdr" --job "reports\job-ID\job.json" --hdr --experimental-av1-hdr
python python/dv_full_file.py "C:\Media\dv-movie.mkv" --experimental-intel --work-dir "C:\Tests\dv" --execute
```

Omit `--execute` for a read-only plan. Use the actual dashboard encoding job
record in `--job`. The AV1 command is research, not ordinary CLI publication:
full verification must pass before adding its output to Plex. It requires
constant HDR10 mastering metadata on every source frame, retains exact dimensions
and original tracks, uses the transparent QSV setting and two-second GOPs,
and rejects outputs saving less than 5%. It validates the complete IVF in a
bounded-memory first pass before writing a repaired copy. Only the reproduced
50000-coordinate clamp is corrected; all picture bytes and IVF timing remain
unchanged. Verification compares every output frame against the source at AV1's
representable MDCV precision, checks copied packets/chapters, decodes the full
output and checks seeking. HDR10+ and Dolby Vision are excluded from this route.

Intel DV full-file research first runs a 30-second preservation/savings test
near five minutes (or near the midpoint for shorter inputs), avoiding reliance
on opening logos. This is a screening sample, not a whole-file savings guarantee.
It requires Profile 8.1, continuous CFR starting at zero, original resolution,
no extra dynamic HDR, and full RPU/frame/track/decode/seek validation. Larger
outputs are rejected. Neither route replaces, renames or removes source media,
installs software, or establishes identical visual quality. Client playback
approval remains separate from automated verification.

### Optional existing-folder cleanup

Cleanup is off by default and uses the existing standalone CLI. Supply the main
video to protect while previewing its containing folder (including subfolders):

```powershell
python python/muxmender.py "C:\Media\Movie (2020)\Movie.mkv" --cleanup-plan "C:\Plans\cleanup.json" --cleanup-samples
```

Without `--cleanup-samples`, only `.nfo` files are nominated. With it, videos
inside directories named `Sample`/`Samples`, or with names ending in a separated
`sample` token, are also nominated. Duration is never used to infer a sample.
The chosen main video, its hard links, ordinary video names, subtitle files at
every depth, artwork and directories are excluded. Links/junctions are not followed.

Inspect every `ready` entry in the JSON preview. Remove unwanted entries or set
their status to `keep`; a sample name alone does not prove the file is expendable.
Explicit apply permanently deletes only the reviewed ready files:

```powershell
python python/muxmender.py --apply-cleanup-plan "C:\Plans\cleanup.json" --execute --confirm-cleanup CLEANUP
```

Apply checks the entire plan's scope and file identities before deletion, then
rechecks each action and the protected video. A durable JSONL journal records
actions. This is not a transactional rollback: earlier deletions remain if a
later action fails. Rebuild the preview before retrying. This option is separate
from `--video-only-folder`, which controls new output folders and never cleans
source folders. Development tests used disposable local fixtures only; this
feature was not applied to Drive Y.
