# AV1 display geometry validation

`mux_integrity.verify_av1_display_geometry` is the shared crop-aware check,
used by the experimental AMD AV1 validation route. It requires decoded-frame
dimension evidence, unchanged sample aspect ratio, and exact known crop offsets.
Probe-reported coded dimensions or crop metadata alone are not enough.

Recognized padded layouts:

- 1920x1080 content in 1920x1082: two bottom padding rows.
- 720x480 content in 768x480: 48 right padding columns, with source SAR retained
  (DVD test: 8:9, producing a 4:3 display).

Missing evidence, unexpected padding, altered SAR, rotation, or crop offsets
fail validation. A caller must pass dimensions measured after decoder cropping
(e.g. FFmpeg showinfo), not uncropped ffprobe frame dimensions. The existing
experimental route checks every decoded frame; sampled checks only establish
evidence for those samples.

The normal publication path remains strict and rejects padded dimensions.
This helper does not enable automatic DVD deinterlacing, broaden the existing
1080p experimental CLI, or certify Plex/client support. A padded output still
needs playback review on the intended client. Source files are never replaced
or deleted by this validation.
