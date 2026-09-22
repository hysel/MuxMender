# Research checkpoint — 22 September 2026

The two TrueNAS research batches finished all 19 commands without a command
failure. They covered **18 unique sources**, not 19: one source was retried with
different settings and passed. Results remain separate copies; no replacement,
cleanup, deployment or production queue change was performed for this review.

## Results after reconciling retries

| Latest outcome | Unique sources |
| --- | ---: |
| Validated output copy | 16 |
| Full output below the selected 10% savings target | 1 |
| No tested candidate met quality and savings together | 1 |

The raw run history contains three keep decisions. One was superseded by a
successful retry, which saved 30.013%. The remaining size rejection saved 8.807%
and deliberately stopped before full validation; it is not an approved output.

The 16 successful sources total **121.331 GB** and their outputs total
**41.419 GB**. That is **79.912 GB (74.424 GiB), or 65.863%, potential reduction**.
Current source/output sizes were read during the review. No space was reclaimed:
originals and separate research copies still occupy storage.

## Evidence reviewed

All 16 output files and sources were present. Each selected trial had three
samples with successful quality, preservation and decoding checks. Selection
source IDs matched the recorded source hashes, and all successful statuses
recorded source and output SHA-256 hashes and retained originals.

Across the selected samples, the lowest mean quality score was 93.271 and the
lowest fifth-percentile score was 90.110. These are sampled VMAF scores, not a
percentage guarantee for every frame. HDR quality uses a common HDR-to-SDR
rendering domain, with native preservation checked separately.

Eight earlier successes have full-decode logs. The eight later successes have
structured strict-decode evidence using the current complete frame audit plus
full audio decoding. This review inspected existing validation evidence and
current file sizes; it did not repeat full decoding, playback or hash all files
again. Replacement must still perform its normal current-file verification.

Private runtime evidence remains under `/work/research-20260921-r9` and
`/work/research-20260921-r26`. Case identifiers are retained rather than media
titles in repository documentation.

## Consolidated code checkpoint

- Keep CLI and app processing on the shared engine and workflow adapter.
- Include the opt-in NVENC peak-rate research setting and its regression tests;
  defaults remain unchanged, with no model-specific encoding branch.
- Include isolated NVIDIA qualification runners and the read-only remote
  research dashboard observer.
- Retain the Pascal representative's validated SDR result and HDR keep decisions
  as scoped evidence, not blanket GPU-family or HDR certification.

See [older-NVIDIA qualification](p4000-qualification-20260920.md) and
[rate-control research](nvidia-rate-control-research.md).

This is a release-preparation checkpoint, not a published release. Docker version
and production settings have not changed. Dolby Vision/HDR10+ automatic routing
is not newly enabled by these results. Git publication and deployment remain
separate approval steps.
