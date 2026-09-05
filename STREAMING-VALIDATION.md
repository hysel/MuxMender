# Streaming validation — 2026-09-04

Standalone CLI, AMD Radeon RX 7800 XT / `hevc_amf`, native Direct3D 11
DV profile 5 reconstruction. Original Star Trek test source opened read-only.
No VS Code restart, Git operation, driver installation, or media deletion.

## Ten-second equivalence check (start 300 seconds)

Output directory: `test-output/stream-test-20260904-214449-435725ce`.
240 frames; original packet timing and copied audio/subtitles verified;
full decode passed. SSIM against the previously retained reconstructed PQ
reference: **0.996766**, matching the earlier disk-based AMD test.
This is a matched-chroma metric, not proof of identical perceptual quality.

## Sixty-second streaming check (start 300 seconds)

Output directory: `test-output/stream-test-20260904-214602-5e1126e7`.
Native reconstruction and AMD encoding took approximately 245 seconds before
final remux/validation. No stall was reported. Sampled working sets were about
1.8 GiB native and 270 MiB FFmpeg; these are observations, not guaranteed caps.

- 1,439 matching original/output frames and normalized presentation timestamps.
- 3832 × 1600, HEVC 10-bit, BT.2020/PQ.
- Audio/subtitle packet hashes and rebased timestamps matched the original clip.
- Full output decode passed; original size and modification timestamp unchanged.
- Original interval video payload: 85,116,705 bytes.
- Encoded interval video payload: 7,766,955 bytes (**90.8749% reduction**).
- Final container: 12,595,134 bytes, including copied audio/subtitles.
- Retained compressed video-only intermediate: 7,778,050 bytes.
- No lossless intermediate was written to disk. All generated media retained.

58 Python tests and six native safety tests passed. Native generated-color
preflight passed. The runtime with streaming support was bundled locally at
`native/muxmender-d3d11/dist/runtime-20260904-214727-e8ab29ba.zip`.

These savings apply only to the tested interval. PQ output intentionally does
not retain Dolby Vision dynamic metadata. The 60-second output still needs
visual/playback review; full-file streaming remains disabled. NVIDIA, Intel,
and streaming CPU fallback have not been hardware-validated by this AMD run.
