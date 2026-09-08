# Hardware support and validation

MuxMender selects encoders by detected vendor and available FFmpeg capability,
not a GPU model name. Listed encoders are only candidates: actual encoding and
per-file verification must succeed. These results describe tested workflows on
Windows, not every GPU, driver, source or Plex client.

## Tested scope (September 8, 2026)

| Hardware | Validated scope | Current entry point |
|---|---|---|
| NVIDIA RTX 5050 | Generated HEVC/AV1 SDR/PQ tests; full Commando SDR and repaired 65 Profile 8.1 playback, including seeking | Normal SDR/HDR CLI; NVIDIA DV remains explicit research |
| Intel Arc B580 | Generated HEVC/AV1 SDR/PQ/irregular timing; full SDR HEVC/AV1, HEVC HDR10, AV1 HDR10 and HEVC DV Profile 8.1 reviewed in Chrome and Sony TV | Normal AV1 HDR repair/verification route; opt-in AMD/Intel DV preservation |
| AMD RX 7800 XT | One full Profile 8.1 episode, 53.7% smaller, user-confirmed Sony TV playback and DV mode | Opt-in preservation; regression against newer shared mux changes still required |

The Intel test setup used driver 32.0.101.8992, FFmpeg/FFprobe 9.0.1 and Python
3.13.15. No driver or tool updates were performed during validation.

## Latest full Intel results

| Output | Original GB | Output GB | Reduction | Verified frames |
|---|---:|---:|---:|---:|
| No Time to Die, AV1 HDR10 | 18.516 | 7.753 | 58.13% | 235,056 |
| House of the Dragon S03E02, HEVC DV 8.1 | 8.833 | 5.697 | 35.50% | 92,034 |
| Reservoir Dogs, HEVC HDR10 | 18.628 | 2.057 | 88.96% | 142,565 |

No Time to Die retains 3832x1596, 10-bit PQ/BT.2020, original audio, chapters and
frame timing. It had no embedded subtitles; a forced-only downloaded track was
replaced with full English subtitles during Chrome review. AV1 mastering-display
metadata uses the format's nearest representable units. The bounded repair only
corrects the reproduced Intel 50000-coordinate clamp; it does not alter picture
payloads. HDR10+, DV and other dynamic metadata are rejected by this HDR10 route.

House of the Dragon retains 3840x1920, frame timing, original tracks/chapters,
static HDR and RPU content/order. The checked Intel CFR/no-B-frame route reconstructs
raw HEVC timestamps before ordered muxing. Full decode and six seeks passed.
No Time to Die passed four seek checks and full audio/video decode. CLI encode/mux
plus source audit took 4,147 seconds (2.36x); later independent verification is
additional. DV encode alone took 1,908 seconds (2.01x). Speeds use different scopes.
No claim of identical visual quality is made.

Both new full outputs passed Chrome/Sony review and subsequent Y-backed playback.
Their original backups were deleted only after separate user approval and fresh
replacement SHA-256 checks. Net savings for these two conversions are 13.899 GB
(50.82%). Media and detailed local reports are not included in Git.

## Preserved boundaries

- Exact resolution by default; no scaling in the specialized HDR/DV routes.
- Dolby Vision defaults to skip. `--preserve-dolby-vision` supports AMD/Intel
  Profile 8.1 only; auto prefers AMD then Intel. NVIDIA remains explicit research.
- AV1 HDR uses the audited pipeline in the normal CLI. Direct unchecked QSV HDR
  command construction remains blocked. Full verification precedes publication.
- A sample and final savings threshold apply to DV. No savings or unsupported
  metadata rejects the candidate; original media and diagnostic evidence remain.
- Intel HDR/DV routes reject CPU fallback and unsupported compatibility-audio
  changes. Ordinary SDR fallback remains an explicit policy choice.
- No automatic installations, source deletion, overwrite, or library replacement.
  Standalone scripts work without VS Code; the optional extension is not required.

Acolyte and a later Long Kiss Goodnight scene did not meet savings requirements.
Dune Part Two, Dogma and Strange New Worlds S04E06 had extra dynamic HDR outside
scope. These are recorded exclusions, not successful conversions. The DV sample
screen now selects near five minutes rather than relying on opening logos.

## Regression evidence

193 unit tests pass. Eight actual Intel generated fixtures pass. Normal CLI
regressions pass 829 AV1 HDR frames at transparent and balanced settings and 960
DV frames after sample preflight, including full preservation/decode/seek checks.
Sparse/empty-subtitle stress tests cover bounded-memory muxing and seeking.

Local evidence entry points:
- `reports/intel-production-integration-tests-20260908.log`
- `reports/intel-integrated-av1-smoke-20260908-cli.json`
- `reports/intel-integrated-av1-balanced-20260908-cli.json`
- `reports/intel-integrated-dv-smoke-20260908/`
- `reports/overnight-readiness-20260907.json`
- `reports/intel-approved-y-publication-20260908.json`
- `reports/intel-approved-y-original-removal-20260908.json`
- `reports/intel-full-reservoir-hdr-20260907-204300/`
- `reports/nvidia-dv-full-65/dv-full-20260906-085358-cbfa0f53/ordered-remux-20260906-103728/`

## Setup and further coverage

FFmpeg/FFprobe must be on PATH or supplied explicitly. AMD uses hevc_amf/av1_amf;
NVIDIA uses hevc_nvenc/av1_nvenc; Intel uses hevc_qsv/av1_qsv. CPU encoders are
libx265/libsvtav1. Missing tools are reported with setup guidance, never installed
silently. See [STANDALONE.md](STANDALONE.md) for commands and
[TODO.md](TODO.md) for AMD regression, broader GPU/client coverage and TrueNAS/Linux.
