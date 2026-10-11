# Choose a smaller viewing copy

Keep **Original resolution** if you want to save space without intentionally
reducing picture dimensions. It remains the default.

Lower-resolution presets make a different trade-off: less detail, smaller files.
They never enlarge a smaller source or crop the picture.

| Preset | Maximum picture size | Video bitrate ceiling |
| --- | --- | --- |
| Original resolution | Source dimensions | Automatic |
| 1080p TV | 1920 × 1080 | 8 Mbps |
| 720p | 1280 × 720 | 4 Mbps |
| 480p | 854 × 480 | 1.5 Mbps |

These are maximum bounds, not fixed output dimensions. A widescreen movie or a
portrait clip keeps its display shape. Audio and subtitles are preserved, so
the complete file's bitrate can be higher than the video ceiling.

## What a passing quality check means

New jobs let you choose **Quality checks** separately from resolution and
encoder tuning. Balanced is the default; Space saver accepts more compression
damage, but still needs to pass every other check.

| Quality profile | Minimum mean VMAF | Minimum fifth-percentile VMAF |
| --- | --- | --- |
| Strict | 95 | 90 |
| Balanced (default) | 94 | 90 |
| Space saver | 90 | 90 |

The selected profile is saved with each job. A failed test never lowers it
automatically. Changing it can re-check an earlier automatic “original kept”
decision. Existing queued jobs retain their recorded settings; older jobs
without a profile keep their legacy thresholds (original 90/90, 1080p 95/90,
720p 93/90, 480p 90/90). Completed replacements and explicit keep decisions
are not undone.

The shared automatic CLI accepts `--quality-profile strict`, `balanced`, or
`space-saver`. Its default is Balanced. The low-level engine preserves legacy
thresholds when that flag is omitted; stricter explicit numeric thresholds
still take precedence.

## Automatic conversion

Choose **Automatic** encoding, a quality profile and either **Create copies** or
**Convert and replace**. MuxMender inspects the source and probes the available
GPU encoders, compares measured candidates, and selects the smallest candidate
that meets your quality and savings requirements. A bounded refinement search
can try additional settings when the first candidates do not qualify. It does
not silently switch to slow CPU encoding or relax your quality profile.

The selected profile and effective thresholds are recorded with the trials,
selection and final status. New trial reports require numeric scores to support
their pass flags. Quality screening uses representative scenes (the whole source
for sufficiently short inputs); full-output validation checks timing, picture
properties, tracks, metadata and decoding. This is not whole-film VMAF scoring.

Actual full-output savings are checked again. A sample estimate does not promise
the same reduction for the entire video. If a check fails or the savings are not
worthwhile, the original stays. Replacement uses the verified publication flow;
copies remain separate when that is the chosen action. Temporary work is cleaned
while compact evidence and history are retained. Existing route-specific
qualification requirements still apply, including pending HDR-to-SDR or HDR
resizing transformations.

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
