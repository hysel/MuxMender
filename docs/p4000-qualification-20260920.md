# P4000 initial hardware qualification

The P4000 is our Pascal-generation representative, not a model-specific product
target. These checks exercise shared capability detection and fallback to a
working hardware codec. They do not certify every Pascal card, driver or older
NVIDIA generation. No separate P4000 encoding implementation is used.

## Full-length SDR follow-up, 22 September 2026

The v35 shared engine completed a separate 43-minute-29-second 1920x1080
BT.709 SDR H.264 input with EAC3 audio and PGS subtitles on the Pascal
representative. The 3,039,233,358-byte input became a 1,734,927,618-byte HEVC
output: **42.916% smaller**, with full-file validation successful and the
test-source hash unchanged. The library original was not modified.

The selected three-scene VMAF means were 97.745, 98.953 and 99.492; the lowest
p5 was 94.097. These are sampled objective measurements, not whole-video
perceptual guarantees or playback approval.

The shared job took 614.9 seconds (10m15s), excluding transfer. Full encoding
took about 193 seconds; the recorded encoding category, including trials, was
199.4 seconds. Frame validation took 368.5 seconds. The complete workflow was
about 4.24 times real-time, while full encoding was about 13.5 times real-time.

Ten-second telemetry samples observed process-tree RSS up to 405.9 MiB, GPU
memory up to 185 MiB and temperature up to 54 C. These are sampled readings,
not guaranteed transient peaks. The GPU encoder reached 100% utilization.
The regression suite ran separately during validation; timings are observed
shared-host results, not an isolated performance benchmark.

Evidence is under `/home/haven42/muxmender-full-sdr-20260922`, with a dedicated
development-dashboard job. The separate output is retained for playback review.
This qualifies this full-length SDR case, not every source or Pascal card.

A regression run from the original v35 build context found a missing research
audit helper and an outdated packaging test fixture. Both were corrected locally;
a fresh test-only bundle ran 640 tests successfully with four environment/context
skips. No deployed app, driver or running conversion code was changed for that fix.

## Real-clip follow-up, 22 September 2026

Separate 30-second SDR and HDR10 excerpts were copied to the isolated test host.
The HDR input is 3840x2076; the shared workflow retains those dimensions rather
than forcing a standard 16:9 frame. Trials use HEVC/AV1 capability detection,
VMAF mean/p5 floors of 90 and a 10% minimum reduction. Sources are not replaced.

The first SDR excerpt was refused because extraction turned a cover image into
a second video stream. That fixture result is retained, not counted as a
conversion pass. The corrected single-video SDR excerpt completed full validation
and was 29.605% smaller, with its source-copy hash unchanged. The detached runner records original-copy hashes
and distinguishes command completion from actual conversion outcomes.

The existing development dashboard at `http://127.0.0.1:8765/` now mirrors this
test group and the separate 19-case TrueNAS research batch. The read-only SSH
observer refreshes every 20 seconds, reports stale connections explicitly and
keeps completed-test counts separate from current-check percentages. It does
not resume production or publish media. The observer runs on the development PC;
remote tests continue independently if that PC sleeps, but live updates pause.

Progress files are under `real-tests` and `sdr-retry` in the test host's
`/home/haven42/muxmender-p4000-20260922` directory. Missing MKVToolNix libraries
were downloaded from configured Ubuntu repositories and extracted under that
same directory, without sudo installation or driver changes.

### HDR rate-control investigation

The first HDR excerpt did not find worthwhile savings within the selected quality
limits. Investigation found that several different CQ settings produced identical
output sizes and scores in the default runtime. A separate 72-frame experiment
showed that an explicit 200 Mbps peak-rate ceiling restored the expected response
to CQ changes. This is evidence from this runtime, not a universal NVIDIA setting.
All 72 decoded lossless diagnostic frames matched the source pixels exactly.

The shared engine and CLI adapter now accept optional `--nvenc-maxrate-mbps`
for HEVC/AV1 NVENC qualification. Defaults remain unchanged. This is a ceiling,
not a target bitrate, and does not bypass quality, savings or preservation checks.
The Windows and Ubuntu suites both ran 640 tests successfully, with three skipped.

Repeating the first HDR case through the full trial workflow with the explicit
ceiling still correctly kept the original: CQ23 saved only 6.207%, below the 10%
minimum, while smaller candidates failed measured quality. Higher-quality settings
were larger. The second independent HDR excerpt also kept its original: the
compact candidate saved 5.482%, below the selected 10% minimum, and smaller
adaptive candidates failed measured quality. Both source-copy hashes remained
unchanged. These outcomes establish tested keep decisions, not a blanket HDR
failure or successful full-output HDR qualification.
Neither diagnostic lossless output nor a completed command counts as an approved
library conversion. No source replacement or production deployment took place.

## Follow-up: current shared engine, 22 September 2026

The P4000 still works with the current shared code (`335157e`) and the existing
driver and portable FFmpeg. No driver update or system package installation
was needed. All tests used generated media, not library files.

- H.264 1080p 8-bit and HEVC 1080p 8-bit / 3840x2076 10-bit probes passed.
- AV1 encoding and H.264 10-bit encoding were unavailable in this runtime.
  Those results did not prevent the working HEVC route from running.
- Repeated successful probes reused their capability cache.
- Both generated HEVC clips decoded and kept their visible dimensions.
- A 12-second 1080p SDR fixture completed the real shared automatic workflow:
  three scene checks, HEVC encoding, full validation and a retained original.
  No encoder mocks or CPU encoding substitutions were used for the candidate.
- The output was 65.834% smaller. Whole-test time, including fixture generation,
  was 15.702 seconds. Scene VMAF means were 99.335, 99.926 and 99.758; each scene
  passed the selected mean/p5 floor of 90. The lowest reported p5 was 98.854.
- The Linux suite ran 636 tests: 633 passed, 3 skipped.

This demonstrates that the older card can use the shared workflow. A generated
lossless test source is easy to shrink; these numbers are not a forecast for
already-compressed movies, and do not qualify HDR or Dolby Vision preservation.
Next qualification work should use a separate representative real-file copy,
then test HDR metadata through the same engine.

Reports are in `/home/haven42/muxmender-p4000-20260922/`: `generated-probes/report.json`,
`shared-sdr-r2/report.json` and `unit-tests.log`. The first end-to-end fixture
stopped before encoding because its output was inside its input tree. The test
layout was corrected for r2; the production safety check was not changed.

The reusable runner is `tools/qualify_nvidia_generated.py`. Its output directory
must be new, and the source is always generated. It never replaces library media.

## Initial checkpoint: 20 September 2026

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
