# TrueNAS v30 — source-driven admission and meaningful validation

Version: `20260919-v30`.

## Changes

- Chapter comparisons ignore muxer-generated IDs and compare exact rational
  timestamps across container time bases. Titles, ordering, intervals and other
  chapter properties remain checked. This fixes the actual HDR quality case A
  HDR10 failure: Chapter 06 was unchanged; only its generated ID differed.
- Equivalent frame-rate and sample-aspect-ratio fractions compare by value;
  output resolution and actual frame timing still must match the source.
- Timestamp tolerances use exact arithmetic: a 2 ms difference no longer fails
  because binary floating point reports 2.000000000000002 ms. Existing 2 ms
  tolerance is unchanged; larger differences remain rejected.
- 8/10/12-bit planar 4:2:0, 4:2:2 and 4:4:4 sources can reach hardware trials.
  The requested format is source-driven. Unsupported hardware rejects its own
  candidate, not the input category. Silent chroma/bit-depth changes still fail
  decoded-frame validation. This is not hardware certification for every format.
- Declared wide-gamut SDR (including BT.2020 with SDR transfer) is admitted.
  PQ and HLG are not treated as SDR or silently tone-mapped.
- Auto hardware discovery tries compiled hardware backends even when container
  GPU inventory utilities are absent. Runtime initialization remains required.
- Adaptive retries are distributed across available encoders instead of letting
  one encoder consume the full retry budget.
- Short videos use shorter sample windows instead of a fixed 60-second cutoff.
  Missing/insufficient decoded evidence and overlapping long GOP samples can
  still prevent a meaningful quality evaluation.
- New UI/CLI requests default to any strictly smaller validated result. The
  minimum-savings control accepts 0–90%; 0 never permits equal/larger files.
  Existing queued requests retain their selected savings thresholds.
- Dashboard job records retain the actual exception, not only the last stage.
- Static HDR10 test v2 preserves source chroma positioning in the HEVC bitstream
  during its no-resize, same-chroma encoding path. It does not relabel arbitrary
  externally resampled files. Original inputs remain read-only.

## Boundaries, not claims of universal support

The automatic queue still has no integrated HDR/Dolby Vision perceptual-quality
evaluator. The standalone HDR10/HDR10+ preservation route does not authorize
automatic replacement. Interlaced video, unusual stream ordering, rotation,
unsupported data/subtitle tracks, RGB and unresolved contradictory metadata
still require implemented preservation paths. No gate is removed merely to
force these cases through an incompatible encoder.

Quality floors remain mean VMAF 90 and fifth-percentile 90 for SDR. Audio/subtitle
payload checks, full decode, source fingerprints, source resolution and verified
publication are unchanged. No media was replaced or deleted for this release.

## Verification

- Windows: 484 regression tests, 3 platform-dependent skips.
- Generated-media smoke: six codec trials, measured selection, full encode and
  validation passed; source hash unchanged. CPU substitutes and relaxed quality
  floors are confined to this tiny orchestration fixture, not production policy.
- Actual failed HDR10 excerpt: 292 frames passed exact HDR metadata, geometry
  and video timestamp checks after source-siting repair; all copied tracks and
  complete decode passed. Original excerpt 58,861,664 bytes; repaired output
  35,980,601 bytes. This is preservation evidence, not automatic HDR quality
  certification or a full-movie saving estimate.

## Deployment

Build from the staged context (does not restart the running app):

```sh
sudo docker build -f /mnt/FR4G/Apps/muxmender/app-build-20260919-v30/deploy/truenas/Dockerfile.app -t muxmender-app:20260919-v30 /mnt/FR4G/Apps/muxmender/app-build-20260919-v30
```

Select `muxmender-app:20260919-v30` in the existing app; keep mounts/history/GPU
settings. Pause admissions and let active jobs finish before deployment,
especially publication. Use Retry skipped/failed for previously blocked files.
Already-successful replacements are not automatically reprocessed.

The revised detached HDR test is independent of the app image:

```sh
sudo bash /mnt/FR4G/Apps/muxmender/hdr10-static-20260919-v2/run.sh
```
