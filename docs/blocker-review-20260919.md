# Eligibility expansion, 2026-09-19 (not yet deployed)

- Default mean VMAF and fifth-percentile floors are 90/90. This is a score,
  not a percentage of retained quality. Minimum default savings remains 10%.
- 10-bit 4:2:0 SDR is admitted without downconverting to 8-bit. Runtime encoder
  probes request 10-bit input; hardware encoders receive P010. Output metadata
  and decoded-frame validation still require the original pixel format.
- Unknown scan type may be recovered from bounded decoded progressive-frame
  evidence. Full frame validation remains mandatory, including repeat/interlace checks.
- Trailing JPEG/PNG cover pictures with filename/MIME metadata are extracted
  byte-for-byte and reattached during sample extraction and encoding. A plain
  FFmpeg remux loses attachment disposition, so it is not used for these images.
  Validation requires identical image packet hashes/counts, metadata and attached
  picture disposition. Unknown codecs, missing attachment tags, interleaved
  artwork and artwork before the movie remain blocked rather than reordered.
- HDR, Dolby Vision, uncertain color declarations and non-4:2:0 formats are not
  silently converted to SDR or assigned guessed metadata.
- A missing transfer tag can remain unspecified when BT.709 primaries/matrix
  and range are declared. No transfer value is guessed. Output stream metadata
  must retain the absence, and decoded-frame checks reject loss of known color
  information. Missing matrix/range still blocks the automatic path.
- UI automatic quality now enables bounded adaptive search. Runtime-tested
  AMD/Intel encoders may try the transparent preset once after baseline failure;
  NVIDIA retains its existing bounded CQ search. Thresholds are unchanged.

## Evidence

Generated 640x384, 24 fps, 10-bit SDR plus PCM audio: AMD HEVC and AV1 passed
72-frame geometry/timing checks, copied-audio packet checks, full decode and VMAF.
HEVC mean/p5: 99.729/99.427; AV1: 99.961/99.966. Both outputs were yuv420p10le.
These small synthetic clips are not real-library quality or savings estimates,
nor proof of NVIDIA/Intel runtime support. A 640x360 AMD test was rejected for
a reported height change; the safeguard was not relaxed.

Read-only preflight of the previous 27 format skips now admits 10: nine 10-bit
SDR files and the previously recovered 8-bit scan-type case. The other apparent
SDR file, DV case C, contains a Dolby Vision configuration
record despite BT.709 stream tags and remains protected.

Passing preflight permits trials, not replacement. Savings, per-scene quality,
full-output validation and publication checks still determine the result.

The three artwork skips also have other blockers: Artwork case B and Color case B lack color declarations after frame inspection;
Artwork case A is HDR. Removing the artwork obstacle therefore
does not increase the current count of newly eligible files beyond ten.

Color case A additionally passes the missing-transfer preservation gate. A retained
raw HEVC test clip passed preservation and VMAF (mean 94.088, p5 92.023) without
tagging the missing transfer value. This is one-scene evidence, not full-file
approval; other scenes still must pass. Potentially eligible count is now eleven.
