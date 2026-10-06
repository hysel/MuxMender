# Tested formats

Current routing: see [supported use cases](SUPPORTED-USE-CASES.md), reviewed
28 September 2026. The table below records earlier qualification milestones;
its older automatic-DV restrictions are superseded by the current inventory.

This page keeps the details behind the [README](../README.md). In plain terms:
some routes have passed real-file tests, others still need work. None of this is
a promise that every file or playback device will behave the same way.

“Validated” below means project testing of the stated route—not certification
by a codec vendor, a guarantee for every file, or universal player compatibility.
Container, video codec, HDR format, GPU/driver and playback device are separate
factors. Each new file still goes through its applicable checks. Research results
do not mean that a route is enabled in the deployed app.

| Format / route | Evidence and current scope |
| --- | --- |
| MKV and MP4 with H.264/AVC → HEVC in MKV | Full-file shared-workflow copies validated on NVIDIA, including MP4 input. See the [research results](animation-research-status-20260921.md). |
| 1080p SDR H.264 → AV1 in MKV | AMD full-file and Chrome/Dolby Vision-capable TV Plex playback tests completed for selected material. The [legacy AMD batch route](AMD-AV1-BATCH.md) has its own narrower constraints; it is not blanket AMD qualification. |
| Previously ripped DVD MPEG-2 → AV1 in MKV | Tested AMD route for 720×480, 8-bit, 8:9 pixel aspect ratio, top-field-first 29.97 fps sources. Explicit deinterlacing approval produces 59.94 progressive output. See [DVD AV1 workflow](dvd-av1-workflow.md). Not certification for every DVD format. |
| Legacy MPEG-4 Part 2 in AVI → HEVC/AV1 in MKV | Source timing/color recovery tested. One full repaired AV1 test copy passed validation and user playback; its damaged source audio required a separately approved repair. Other candidates missed size or quality targets. Not unrestricted AVI qualification. |
| 10-bit 4:4:4 H.264 input | Three-scene tests passed on four selected sources; full-file qualification remains pending. |
| 4K PQ/HDR10 HEVC → HEVC in MKV | Selected full-file validation passed, including native HDR preservation. A smaller candidate can still be rejected for quality. No fixed 16:9 resolution requirement. |
| Dolby Vision Profile 8.1 | Integrated NVIDIA route with selected full-file evidence. Each candidate must pass quality, preservation and savings checks; some tested settings correctly failed. |
| Combined Dolby Vision Profile 8.1 + HDR10+ | Integrated preservation route with selected full-file evidence. A v41 static-metadata mismatch remains under investigation; this does not certify every input. |

HLG, other Dolby Vision profiles, additional pixel formats and other container/
hardware combinations are **not broadly certified** by this list. Recognition
by the scanner or support advertised by FFmpeg is not sufficient evidence.
Audio/subtitle copy validation likewise does not guarantee that every player can
direct-play the copied tracks.

Hardware qualification is also specific: the [Quadro P4000 tests](p4000-qualification-20260920.md)
verified generated HEVC clips, not real-library HDR/DV quality. Do not infer that
all NVIDIA, AMD or Intel generations support the same codecs or settings.
