# v25 — Bounded frame readers and early impossible-size rejection

Includes all v24 packet-pass improvements, v23 QA fixes and v22 workspace changes.

- SDR auto mode uses two software-decoder threads per frame reader rather than
  FFprobe's automatic count. All frames, timestamps, geometry, colors and side
  data are still collected. No GPU decoder or frame skipping is introduced.
- Metadata already read in the current validation step supplies duration/start
  time to the frame scanner; no duplicate metadata probe is needed there.
- Stop a candidate when its completed sample bytes exceed the size budget for
  **all three** reference clips, even if unencoded clips were zero bytes. This is
  rejection-only evidence, not extrapolation from one scene. Successful candidates
  still need all three clips and every existing quality/preservation check.
- The selector independently recomputes the size bound. Incomplete/failed/unknown
  or duplicate sample evidence cannot become a successful or cacheable result.
- Reject dangerous frame side data even when emitted on a separate compact line.

## Measurements

Generated 10-second 720x480 fixtures, three alternating-order comparisons:

| Frame scan | Automatic threads | Two threads | Reduction |
| --- | ---: | ---: | ---: |
| H.264 | 0.131 s | 0.105 s | 19.8% |
| HEVC | 0.221 s | 0.153 s | 30.9% |
| AV1 | 0.503 s | 0.400 s | 20.5% |

240 decoded frames per SDR fixture pass the existing timing/geometry/color
comparison. Both readers retain mastering-display/content-light metadata and
reject a generated HDR fixture. Harmless unregistered SEI repetition can differ;
raw evidence files are not claimed byte-identical. Sources remain hash-identical.

These are short local measurements, **not full-library or TrueNAS throughput**.
Hardware/FFmpeg builds/content can change results. Two threads bound contention
between workers, but are not a universal optimum. Re-test real jobs after deploy.

Full output decoding with error rejection, audio/subtitle payload checks, frame
counts, quality thresholds, source/output hashes and publication checks remain.
Combining the full decode pass with frame inspection is NOT enabled: equivalent
error and audio coverage has not been established. No months-to-days claim.

Regression: 423 tests run, 3 skipped, no failures. Generated-media full workflow
smoke passed using mocked CPU encoders (not a production quality certification).
Qualification tool: `tools/qualify_frame_reader.py`. Early rejection integration:
`tools/smoke_auto_optimize.py --early-screen-only` (plus normal tool/path arguments).

## Deployment

```sh
sudo docker build -f /mnt/FR4G/Apps/muxmender/app-build-20260918-v25/deploy/truenas/Dockerfile.app -t muxmender-app:20260918-v25 /mnt/FR4G/Apps/muxmender/app-build-20260918-v25
```

Switch the app to `muxmender-app:20260918-v25` after active work finishes. Existing
mounts, environment, GPU assignments and quality settings remain unchanged. No
source changes, queue restart or deployment is performed by staging this release.
