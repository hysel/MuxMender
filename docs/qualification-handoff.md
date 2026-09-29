# Conversion-blocker qualification checkpoint

This checkpoint separates working research code from a deployed application.
The full remote regression suite passed 845 tests. The production app and queue
were not changed, and no library originals were replaced by this research.

## Evidence reviewed

The identifiers below locate private research reports under `/work` on the
isolated TrueNAS research host. They are not media names. Generated-fixture
savings prove that a workflow can finish; they do not forecast library savings.
Several small fixtures deliberately used a zero-percent savings threshold to
exercise the pipeline. Production thresholds were not changed by those tests.

| Requirement | Observed result | Research evidence |
| --- | --- | --- |
| Short and subsecond sources | Complete-source evaluation passed, including a subsecond DV input with six frames. | `short-source-20260923-r3`, `container-subsecond-20260923-r1`, `dv-short-auto-subsecond-20260923-r1` |
| Rotation and original dimensions | Rotated-source conversion passed without baking rotation into changed dimensions; native MP4 preservation also passed. | `rotation-full-20260923-r3`, `container-long-20260923-r5` |
| AAC timing and native containers | MP4 output passed the full workflow when MKV could not preserve source timing. MOV retained a data track. | `container-long-20260923-r5`, `data-track-full-20260923-r1` |
| Additional tracks and variable timing | DV output retained secondary video and copied tracks with a nonzero, variable presentation timeline. | `dv-multitrack-endtoend-20260923-cq18`, `profile5-tracks-20260923-r1`, `mel-tracks-20260923-r1` |
| Other picture side data | Generated stereo metadata survived the full conversion workflow. This is not evidence for every possible side-data type. | `stereo-full-20260923-r2` |
| Stale DV declarations | Complete primary HEVC inventories proved absence of RPU/enhancement data before recovery; HDR and SDR full conversions passed. Sampled absence is insufficient. | `stale-dv-recovery-20260923-r4`, `stale-dv-recovery-20260923-sdr` |
| Interlaced fallback | H.264 passed both field orders, field/frame quality and timing checks, with smaller output. HEVC/AV1 initialization failures remain backend-specific. | `interlaced-quality-20260923-r2`, `interlaced-auto-20260923-r1` |
| Genuine Profile 5 handling | The automatic CLI validated 288 generated Profile 5 frames through native DV rendering. Separate extra-track/timing coverage also passed. Not real-title certification. | `profile5-cli-20260923-r3`, `profile5-tracks-20260923-r1` |
| Profile 7 MEL | Complete EL/RPU preservation and both native-DV and HDR10 fallback quality passed over 288 frames. | `mel-native-20260923-r1` |
| Profile 7 FEL | A real 246-frame excerpt passed native reconstruction, fallback quality and independent preservation checks; 55.56% smaller with the current image's FFmpeg. | `fel-stock-tools-20260923-r2` |
| Mixed MEL/FEL | All 246 alternating-metadata frames passed the renderer comparison; shared routing now selects reconstruction when any FEL is present. This test is synthetic. | `fel-mixed-runtime-20260923-r1` |
| Shared app behavior | MP4/MOV result acceptance and copy-only qualification handling now match the shared contract. Missing evidence and unsafe outputs remain rejected. | `test_control_service.py`, remote 844-test suite |

## Remaining work and limits

- The isolated image built and passed automatic FEL conversion as UID 568 with
  bundled runtime discovery, a read-only root filesystem, no network or library
  mount, and 4-CPU/8-GiB limits. The sample was 55.56% smaller. Image identity:
  `sha256:cd499921732cf200729663d3eb4377623966a92145d4cf4ea3206f407045fff8`.
  This image was not deployed. Its separate Profile 5/MEL GPU-rendering follow-up
  also passed as UID 568: generated full-copy reductions were 74.76% and 79.30%,
  respectively, with sources unchanged and publication disabled. The systemd
  launch finished with exit status zero. These are fixture results, not predicted
  savings for real titles.
- Finish source/notice delivery review before distributing the bundled runtime.
- New Profile 5/7 outputs remain separate copies. Their automatic replacement
  flag must not be enabled merely because sample conversion succeeded.
- Physical AMD/Intel work is deferred by the user's NVIDIA-only Phase 1 scope.
  The shared routing code does not certify untested devices or driver builds.
- Truly unreadable/corrupt input, failed reconstruction, changed tracks/timing,
  insufficient quality or savings, and insufficient resources remain legitimate
  reasons to retain an original. Report actual evidence, not a format blacklist.

The scoped NVIDIA Phase 1 blocker investigation and separate-copy qualification
are complete. Physical AMD/Intel work is deferred, not certified. Release
preparation and replacement enablement are separate follow-up work: this evidence
does not authorize a release, source replacement, production queue changes or
git publication.
