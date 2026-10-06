# Choose a smaller viewing copy

Keep **Original resolution** if you want to save space without intentionally
reducing picture dimensions. It remains the default.

Lower-resolution presets make a different trade-off: less detail, smaller files.
They never enlarge a smaller source or crop the picture.

| Preset | Maximum picture size | Video bitrate ceiling | Quality score: mean / fifth percentile |
| --- | --- | --- | --- |
| Original resolution | Source dimensions | Automatic | Existing policy, normally 90 / 90 |
| 1080p TV | 1920 × 1080 | 8 Mbps | 95 / 90 |
| 720p | 1280 × 720 | 4 Mbps | 93 / 90 |
| 480p | 854 × 480 | 1.5 Mbps | 90 / 90 |

These are maximum bounds, not fixed output dimensions. A widescreen movie or a
portrait clip keeps its display shape. Audio and subtitles are preserved, so
the complete file's bitrate can be higher than the video ceiling.

## What a passing quality check means

For a resized copy, we compare it against the original **resized to the selected
dimensions**. This checks compression damage at that resolution. It does not
claim that a 480p copy retains all the detail of a 4K original. VMAF scores are
screening measurements, not percentages of quality preserved.

Timing, audio, subtitles, track roles and chapters still need their checks.
The output must also meet your savings target. A preset never guarantees that
a video will be converted: a candidate can fail quality, bitrate or preservation.

Replacing an original with a lower-resolution output permanently loses detail.
Use **Create copies** to compare results before authorizing replacement.

## Plex compatibility

The 1080p / 8 Mbps and 720p / 4 Mbps targets follow Plex's documented
[optimization presets](https://support.plex.tv/articles/213095317-creating-optimized-versions/).
Plex also documents [480p / 1.5 Mbps streaming](https://support.plex.tv/articles/115007570148-automatically-adjust-quality-when-streaming/).
These are target choices, not a blanket Direct Play guarantee. Codec, bit depth,
frame rate, container, audio, subtitles and player capabilities still matter.
MuxMender retains its playback-verified codec selection and track preservation
policy; it does not duplicate Plex's optimizer's audio or subtitle conversions.

## HDR is your choice

Each request records **Keep HDR** or **Convert to SDR**. Converting to SDR changes
how highlights and colors are presented and removes HDR presentation.

This feature is still in development. Generated progressive SDR conversions
have passed all three preset targets, including generated RTX 5050 H.264, HEVC
and AV1 outputs with complete validation and target-resolution VMAF checks.
Real-media presets, resized interlaced output, HDR resizing and HDR-to-SDR output
are pending. Unsupported
new transformations retain the source with an explanation, not an untested
conversion. Existing original-resolution preservation routes remain unchanged.
