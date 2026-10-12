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

### Age filters and time limits

Use the creation-age filter to select all files or recently created files by
hours, days or weeks. Filesystem dates may reflect copying rather than when a
video was made.

A processing time limit applies to individual stages, not the entire batch.
Change it before adding jobs. New settings don't rewrite requests already in
the queue.
