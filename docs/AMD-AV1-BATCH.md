# Safe sequential AMD AV1 batch workflow

Standalone Python CLI; no VS Code required. This experimental route is only for
progressive 1920x1080, square-pixel, 8-bit SDR H.264 sources on supported AMD AV1
hardware. It does not change HEVC/NVIDIA/Intel defaults or process HDR/Dolby Vision.
QP80 was playback-tested on Series B and Series C; it is lossy, not universal quality.

## Plan first (default is dry-run)

```powershell
python -B python/amd_av1_batch.py "Y:\TV\Series C\Season 1" --output-dir "E:\MuxMender-TestOutputs\batches" --dry-run
```

The recursive metadata plan prints JSON, never initializes the GPU, creates no
output directory and never changes source media. It shows eligibility/skip reasons,
not guaranteed savings or health. Already HEVC/AV1 files are kept as-is. Damaged
files can still look eligible in metadata; execution adds a full packet/container
scan and full-file validation. Those checks reject detected errors but are not a
claim to identify every possible defect.

## Execute a bounded batch

```powershell
python -B python/amd_av1_batch.py "Y:\TV\Series C\Season 1" --output-dir "E:\MuxMender-TestOutputs\batches" --execute --max-files 3
```

Supply `--ffmpeg`/`--ffprobe` paths if absent from PATH. Installed entry point:
`muxmender-batch-amd-av1`. Only one file runs at a time. The default limit is **one
attempted candidate** per invocation; set a positive `--max-files` explicitly for
larger batches. Failed candidates consume the limit; unsupported/already-validated
files do not. Remaining candidates are recorded as deferred, not silently processed.

Each candidate gets:

- Source size/mtime recheck and a full read-only container packet scan.
- Existing AMD encoder availability check; no installations or CPU fallback.
- Twice-source-size free-space check plus 5 GiB reserve; reserve checks while working.
- Unique full-copy output, no overwrite, no scaling, original tracks retained.
- Source SHA-256 before/after, decoded frame count/timing, every displayed frame's
  dimensions, copied audio/subtitle packets, chapters/track metadata and full decode.
- At least 5% measured total savings before being recorded as validated.
- An output SHA-256 in `amd-batch-completed.json` for subsequent-run verification.

The reviewed two-row coded AV1 padding exception still requires crop-aware playback.
No files are promoted to Plex, copied to Y:, replaced, renamed or deleted by this
batch command. Failed media and reports remain. Automated checks do not guarantee
perceptually lossless results; spot-check new content and investigate exceptions.

## Re-run, cancellation and reports

Re-run the same command/output root to continue. Completed entries are skipped
only if source identity and source/output SHA-256 still match. Missing/changed
outputs are not trusted. Failed/deferred files may be retried; each attempt uses a
new directory. There is no automatic retry loop within one invocation.

`AMD-BATCH-*/batch.json` records validated, failed, skipped and deferred files.
Progress appears in the terminal and existing local dashboard. Each full-file
conversion retains its own validation report under that batch directory.

A `.amd-batch.lock` prevents simultaneous batches using the same output root.
After a crash, verify the recorded process has ended before manually removing
that metadata lock. The command never automatically steals a stale lock.

Ctrl+C stops the batch. Creating a `STOP` file in the printed batch directory
requests a stop at the next guard check; some blocking probe/checksum operations
must finish or time out before observing that request. Source media and partial
outputs remain. Disk/cancellation/hardware stops do not advance to another file.
Ordinary per-file integrity failures are recorded and processing continues within
the requested limit. Nonzero exit means errors or interruption; inspect reports.

Use an output directory disjoint from the input tree. Do not edit source files
while a batch runs. This command never calls the library planner's cleanup APIs.
