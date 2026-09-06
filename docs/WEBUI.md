# Local Web UI and standalone planner

Requires Python 3.10+ and FFmpeg/FFprobe. No Node, VS Code, Plex or web framework
is required at runtime. From the project folder:

```powershell
python python/webui.py
```

Open http://127.0.0.1:8766. The original read-only dashboard remains available
via `python python/dashboard.py` on port 8765. The Web UI includes a link to historical
jobs and reads prior `reports/**/files.jsonl` inventories, including the TV scan.
Use `--ffmpeg PATH --ffprobe PATH` when the executables are not on PATH.
Use `--root PATH` for a separate project/report root and `--port NUMBER` to change
the local port. Run as your normal user; do not expose it through a reverse proxy.

## Workflow

1. Enter an absolute file/folder path and start a read-only metadata scan.
2. Refresh the saved-scan list when it completes and select a scan. Results are
   paginated. Filter by recommendation and/or case-insensitive file/folder text,
   then Apply filters. Counts reflect matching records across the entire scan,
   not just the visible page. `preview-candidate` is not a promise of savings or visual quality.
3. Select a candidate, select GPU/codec, choose preview or full episode, and
   check the explicit approval box. Preview range is 1–30 seconds; keyframe
   preroll can make the actual reference slightly longer. Resolution is fixed
   to the original dimensions; there are no scaling controls in this version.
4. The serialized queue writes to a fresh `reports/webui-jobs/<id>` directory.
   The source is never an output. Source size/mtime is rechecked against the
   scan (or captured on selection for legacy reports).
5. Results report real size savings, validation outcome and output path. Review
   playback before approving larger work. No automatic Plex publication or
   source replacement happens. Unsupported/uncertain outputs remain retained.

Only ordinary progressive SDR H.264 candidates are supported by this first Web
UI conversion route. Unknown color, field order, rotated video, legacy codecs,
HDR, and Dolby Vision are blocked or routed to review. The existing opt-in AMD
DV8.1 CLI remains available separately; no DV preservation gate was bypassed.

Missing stream-level color fields can be recovered from consistent explicit
color values in the first eight decoded frames (at least two frames required).
Missing or conflicting frame values remain unknown. This is evidence recovery,
not a resolution-based color guess or a guarantee of constant color metadata
throughout the entire file.

HEVC/AV1 hardware selection is capability-based; execution may still fail on a
particular driver/GPU. CPU must be selected explicitly; there is no fallback.

The tested AMD settings are quality preset with QP I=21/P=23, matching prior
previews. Other vendors use the existing balanced encoder options, which require
separate hardware and playback validation. The worker validates dimensions,
bit depth, color tags, aspect ratio, video packet count/PTS, audio/subtitle packet
hashes/timestamps, chapters, attachments, and full output decoding. Packet count
is not a perceptual metric. Preview checks compare to the extracted reference;
they are not proof of original-to-reference frame equivalence at every boundary.

An omitted audio packet duration is accepted only when the next same-stream PTS
confirms the provided duration; payload hashes, PTS and skip/padding metadata
must still match. Missing initial DTS can occur in valid H.264 B-frame files.
A bounded initial omission is accepted only within the reported reorder delay,
with increasing subsequent DTS and matching decoded presentation timestamps.
At nonzero seek positions only, bounded leading pictures before the first key
picture may be excluded from sampled frame comparison. At the source beginning,
every sampled packet must match a decoded frame. No timestamps are rewritten;
missing PTS, later DTS gaps and unmatched frames remain blocked. These sampled
checks do not replace full output timing/content validation after encoding.

Audio/subtitle packets are compared independently for each stream identity,
preserving packet order within each track. Container interleaving across tracks
is not required to be identical. Payload, timing, side-data and packet-count
differences within a track still fail validation.

For audio duration differences, a full decoded-frame metadata check can establish
rounding evidence: unchanged frame timestamps, sample counts and side data,
one frame per packet, and matching sample rate/time base. Both packet durations
must be the floor or ceiling in container ticks of the exact sample duration.
Only clocks at least as precise as 1 ms are supported. This does not relax
packet payload, presentation timestamp, padding, or subtitle checks. Reports
count accepted rounded durations. These extra full-track reads may take minutes.

To revalidate an existing full-file Web UI output without encoding again:

```powershell
python python/revalidate_output.py reports/webui-jobs/JOB_ID
```

This writes a fresh report and a dashboard history job, leaving the original
job outcome and both media files unchanged. It is a standalone diagnostic;
run it when the conversion queue is idle to avoid competing disk reads.

## Queue and recovery

Later `revalidation-*.json` outcomes are displayed without rewriting the original
execution records. Playback approval is recorded separately in
`playback-review.json`, tied to an exact validation report; an older approval
does not approve a newer run. Missing local output is shown explicitly.
These are report-only updates, never media deletion or modification endpoints.
The earlier execution failure remains visible as labeled history.

See NVIDIA-HANDOFF.md for the pending hardware-generic test sequence on the
second machine. No Git transfer or NVIDIA execution is implied by that checklist.

- One job runs at a time in this controller, including scans/dependency checks.
  An OS file lock prevents two controllers sharing a queue. This does not prevent
  a separate manually launched legacy CLI from using the GPU concurrently.
- Full conversions require twice source size plus 2 GiB available. Previews
  reserve up to 2 GiB for artifacts plus a 2 GiB free-space floor. The guard checks
  free space during FFmpeg stages. Estimates do not guarantee output size.
- Cancel writes an owned STOP marker; the worker stops cooperatively and retains
  all files. A probe already in progress can delay cancellation up to its timeout
  (normally 60 seconds, some full validation probes up to 600 seconds).
- Closing the controller asks the active worker to stop. Parent-process checks
  also stop work if the controller disappears. During blocking validation probes
  the same timeout caveat applies. No unrelated process is killed.
- After a restart, unfinished queued jobs are marked interrupted and **never
  resume automatically**. Reselect and approve a new job; partial media remains.
  Startup is blocked if an earlier owned worker may still be running.
- FFmpeg stages cap runtime at four hours and progress stalls at 120 seconds.
  General workflow outputs below the selected savings threshold fail acceptance.

## Read-only CLI planner

```powershell
python python/library_planner.py "Y:\TV"
```

Writes a unique local report directory with `files.jsonl` and `summary.json`.
Known generated report/output roots should be excluded when scanning a project;
the Web UI excludes its `reports` and `test-output` automatically. Symlink and
junction subdirectories are not traversed. Folder-access failures stop the scan;
individual probe failures are recorded, not silently treated as successful.
Savings estimates remain null until actual matched-segment tests are performed.

## Setup

```powershell
.\powershell\setup-windows.ps1                 # audit only
.\powershell\setup-windows.ps1 -Install        # confirmation before each package
.\powershell\setup-windows.ps1 -Install -IncludeGit
```

If PowerShell blocks script execution, inspect the file and follow your Windows
policy; the script does not change execution policy. It never installs drivers,
build tools, or optional Dolby Vision software, and never runs encoding. Git is
optional for downloading updates, not required to use MuxMender.

## Security and limits

Loopback binding, Host validation, same-Origin checks, JSON-only bounded requests,
and a random per-session token protect mutation endpoints. No shell commands,
arbitrary executables, arbitrary file downloads, media deletion, or installation
endpoints exist. Executable paths are operator-only launch options. Local users
who can access this process can read media paths and logs; this is not a
multi-user authenticated server and is not suitable for LAN/cloud exposure.

The Web UI writes its own metadata atomically but never removes media. Filesystem
permissions remain the ultimate boundary; for stronger protection, mount source
libraries read-only. Browser visual QA was not requested; automated HTTP/security,
source, and workflow tests are recorded separately. No background autostart is
installed. Keep the server terminal/process running while using the UI.
