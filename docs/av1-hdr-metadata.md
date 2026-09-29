# Keeping HDR brightness information with AV1

An encoder can leave out content-light metadata even when the source explicitly
records both values as zero. Missing and explicitly zero are not treated as the
same thing by our preservation checks. This does not mean the picture itself was
damaged, but it prevents us from approving the conversion as fully preserved.

The shared engine can now restore these records when **every inspected source
frame has the same complete values**. It copies compressed video packets and
adds only the content-light record. It does not re-encode the picture, invent
brightness values, or round the source mastering-display values. Sources with
changing or missing records continue through ordinary validation; this helper
does not certify them.

The repair uses optional PyAV 18.1.0. Standalone installations can install the
`hdr-av1` extra. The TrueNAS Docker recipe pins the tested Linux x86-64 wheel by
SHA-256 and keeps it separate from the system Python packages. Without this
dependency, ordinary AV1 evaluation remains available, including its unchanged
metadata checks. Preparing this Docker recipe is not an image build or deployment.

## What has passed

On an isolated NVIDIA research system, a 252-frame real excerpt passed the full
shared HDR metadata, frame timing, audio/subtitle/artwork, and decode checks after
repair. Common-render quality scored 97.33 average and 95.44 at the fifth
percentile, above the unchanged 90/90 thresholds. These are metric scores, not
percentages of perceptual quality. A generated fixture also verifies identical
decoded picture hashes, unchanged timestamps, and refusal to overwrite files.
The repaired real excerpt independently matched the encoder output's full
decoded-picture SHA-256 as well; the repair did not change its pictures.

This is bounded sample evidence, not full-library certification. The tested
excerpt grew slightly, so it is **not** a space-saving result. Full conversions
still need to pass the normal quality, preservation and final-size checks.
No original files were changed and no reclaimed disk space is claimed.

The discarded IVF/mkvpropedit approach is not used: it lost container mastering
data and then rounded some values when restoring them. The strict validator
caught both issues. Packet-copy remuxing retains the original codec parameters
instead. Generated intermediates are recorded by the normal artifact manifest
and cleanup routines, including outputs of interrupted commands.
