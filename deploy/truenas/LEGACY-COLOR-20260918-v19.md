# Legacy SDR color inspection and bounded tests

Includes v18 parallel processing and all previous staged updates.

Missing stream color tags trigger read-only FFprobe inspection at three positions
(24 video packets each, 60-second timeout). Decoded frames expose decoder/bitstream
color declarations; no resolution/filename heuristic invents tags. Consistent
declared tags can fill missing fields. Conflicts, HDR/DV/geometry side data and
unsupported formats remain blocked. This is sampled evidence, not proof that a
tagless source was authored with a particular color interpretation.

Explicitly tagged progressive 8-bit legacy SDR matrices/primaries including
SMPTE 170M and BT.470BG are preserved instead of forced to BT.709. Interlacing,
10-bit and HDR support are not expanded. Full decoded-frame evidence now also
checks conflicting declared color properties and rejects HDR transfer functions.

Advanced settings: `Missing color information` defaults to inspection without
guessing. The optional `BT.709 limited range` assumption works only for Inspect
or Test samples. Choose Recheck for old skipped decisions. UI/backend block full
conversion and replacement with the assumption; CLI blocks assumed full encoding,
and publication independently rejects a plan recording assumed color. VMAF,
geometry, timing, audio/subtitle integrity and source hashes remain mandatory.
Metric scores cannot confirm an assumed color interpretation. Source media is
never retagged. The test's effective tags and provenance are saved in plan.json;
unsupported results include color_inspection in eligibility.json.

Actual read-only inspection: 72 frames from three regions of Suicide Squad Hell
to Pay all lacked the four color fields. No source changes or real GPU encoding
were performed for this update. Sample playback testing remains necessary.

After current work drains:

```sh
sudo docker build -f /mnt/FR4G/Apps/muxmender/app-build-20260918-v19/deploy/truenas/Dockerfile.app -t muxmender-app:20260918-v19 /mnt/FR4G/Apps/muxmender/app-build-20260918-v19
```

Set image tag `20260918-v19`. No mount/environment changes.

References: https://ffmpeg.org/ffprobe.html (read_intervals/show_frames),
https://www.ffmpeg.org/ffmpeg-filters.html (color metadata vs pixel transforms).
