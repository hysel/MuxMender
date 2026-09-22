# P4000 initial hardware qualification

Host: 192.168.1.212, Ubuntu 26.04.1, user haven42. Quadro P4000 8 GiB,
compute capability 6.1 (Pascal), driver 580.178.04 unchanged.

Portable BtbN FFmpeg n8.1.2-267-gb2f422d306-20260920 installed without sudo in
`/home/haven42/muxmender-p4000-20260920/ffmpeg-n8.1-latest-linux64-gpl-8.1`.
Downloaded archive SHA256 verified against GitHub release asset digest:
`469a44b4d951eae7e6f6b61858e948104d541a631322ef26efc5e17b3a521062`.
Source: https://github.com/BtbN/FFmpeg-Builds/releases

Tests use v33 shared encoder_capabilities, no mocked encoders, no library media.

| Probe | Result |
| --- | --- |
| H.264 NVENC, 1080p 8-bit | Working |
| H.264 NVENC, 3840x2076 10-bit | Unavailable in this runtime |
| HEVC NVENC, 1080p 8-bit | Working |
| HEVC NVENC, 3840x2076 10-bit | Working |
| AV1 NVENC, both formats | Unavailable in this runtime |
| Repeat successful probes | Positive cache reused |

Two generated 2-second HEVC clips using balanced p6/hq/VBR/CQ21 passed
software decode and exact visible-dimension checks. 1080p took ~0.34 seconds
and 3840x2076 Main10 ~0.86 seconds including process startup; these tiny
synthetic clips are NOT representative movie throughput or quality benchmarks.

Report: `/home/haven42/muxmender-p4000-20260920/generated-tests/report.json`.
No driver changes, system package installs, service restarts or media replacements.
HDR/DV preservation and real-video quality/savings are not certified by this test.
The qualification script was added after the immutable v33 archive was staged;
the tested shared implementation is from that v33 archive.
