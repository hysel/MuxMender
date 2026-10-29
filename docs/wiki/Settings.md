# Choose quality and size settings

You don't need to tune every setting. Automatic encoding, original resolution
and Balanced quality are a useful starting point.

## Encoding

**Automatic** tries suitable encoders available on your GPU and compares the
results. It selects a smaller candidate only when it meets your chosen checks.
It doesn't quietly fall back to a slow CPU encoder or lower your quality setting.

A codec name alone doesn't tell you whether a file can shrink. An older H.264
file may already be compact; a newer codec may still have room to improve.

## Quality

- **Strict:** prioritize a closer match to the original.
- **Balanced:** the default compromise between picture quality and space.
- **Space saver:** allow more compression damage while keeping the other checks.

These settings use measured picture comparisons, not a literal percentage of
quality preserved. Audio, subtitles, timing and other preservation checks still
apply. The app doesn't lower the selected profile when a candidate fails.

## Resolution and HDR

**Original resolution** keeps the source dimensions. Lower-resolution presets
deliberately lose detail to make smaller viewing copies:

| Preset | Maximum dimensions | Video bitrate ceiling |
| --- | --- | --- |
| 1080p TV | 1920 × 1080 | 8 Mbps |
| 720p | 1280 × 720 | 4 Mbps |
| 480p | 854 × 480 | 1.5 Mbps |

The picture keeps its shape; these are bounds, not a promise to stretch every
video to those dimensions. Audio can make the total bitrate higher.

Where your release supports it, choose whether to keep HDR or convert to SDR.
SDR conversion changes the presentation of colors and highlights. If a requested
transformation isn't supported, the app keeps the source with an explanation.
Start with copies when changing resolution or HDR. A Plex-friendly target isn't
a guarantee of Direct Play on every Plex client.

## How much space should a conversion save?

The default size-aware target asks for the smaller of **25% or 1 GB**, with a
**100 MB minimum**. For example, a 2 GB file needs to save 500 MB; a 20 GB file
needs to save 1 GB. The preview shows each file's requirement.

You can choose a fixed percentage instead. Samples estimate the saving; the
finished file must meet the actual requirement too.

## Other options

### GPU encoding and file checks

A GPU can encode a video while other steps still use the CPU or storage. An
idle GPU during inspection or validation does not necessarily mean the job is
stuck. Look at the current step and its last update before changing settings.

Some checks can use the GPU only after that GPU and driver combination has been
tested. Otherwise, they run on the CPU; GPU encoding can still work. Don't copy
another server's acceleration record or disable quality checks to speed things up.

The app checks GPU inspection automatically. On the first matching video, it
uses the complete CPU reference to compare every GPU frame and tests deliberately
damaged generated clips. This first check adds work; later matching jobs reuse
the saved result. No host script or extra qualification mount is required.

Results stay in private app storage under the output folder. Keep this storage
when upgrading. A changed reader, GPU, driver or compatibility policy can require
a fresh check, which the app handles itself. If a path cannot be qualified or
would be slower, inspection stays on the CPU. Encoding can still use the GPU.

With a resource profile that allows parallel work, two different GPU stages can
share spare capacity after 30 seconds of healthy readings. Busy GPU engines,
limited memory, storage pressure or another app needing the GPU delay new starts.
The checks applied to each video stay the same.

The app also checks for a newly verified GPU reader while an
inspection is waiting for resources. If another job has completed the matching
qualification, the waiting check can switch before it starts. This needs no
setting change. An inspection already running is allowed to finish.

### Age filters and time limits

Use **File creation date** to select all files, files **Created within the last**
interval, or files **Older than** an interval. Enter an age in minutes, hours,
days or weeks. For example, **Older than → 2 → Days** leaves recent additions
alone. The preview shows which files match. Filesystem dates may reflect copying
rather than when a video was made; files with unavailable creation dates are
excluded when filtering.

A processing time limit applies to individual stages, not the entire batch.
Change it before adding jobs. New settings don't rewrite requests already in
the queue.

## Encoding speed (next release)

For videos at least five minutes long, automatic encoding can compare up to two
faster NVIDIA presets after finding a passing option. It uses the same source
scenes and your chosen quality and savings targets.

A faster choice must take at least 20% less measured encoding time, be no slower
on any tested scene, and produce samples no more than 5% larger than the smallest
passing option. Its projected encoding time saving must also exceed the time
spent comparing presets. The projected extra space is also capped at 512 MiB per video.
A preset that misses the first-scene speed target is stopped before its remaining
clips and quality checks. If timing evidence is missing or too short to compare,
the smallest passing option stays selected. Sample timings are estimates; the full file still needs
all normal checks before it can replace an original.
