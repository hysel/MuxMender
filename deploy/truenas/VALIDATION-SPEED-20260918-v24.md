# v24 — Fewer validation passes

Includes all v23 QA fixes and v22 workspace/history features. No quality threshold,
resolution policy or publication safeguard has been relaxed.

## Changes

- Collect packet hashes/timestamps in one demux pass per file, then split evidence
  by stream using bounded memory. Compare packet ordering within each copied
  audio/subtitle track; allow cross-track interleaving to differ after remuxing.
- Six copied tracks now need two media scans rather than twelve. Video packet
  hashes are emitted by FFprobe but not compared because video was re-encoded.
- Reuse generated reference-clip packet evidence across candidate tests within a
  single job. Rehash both clip content and cached evidence before every reuse.
  No stat-only or cross-job cache; full library files are not cached here.
- Reject missing/malformed packet identities/hashes and nonfinite packet timing.
- Combined packet scans report media-time progress rather than an unknown percent.
- Keep source/output frame scans, full decoding, copied payload/timing comparison,
  source hashes, output hashes, size gates and verified publication unchanged.

## Measurements and limitations

Three alternating-order rounds on a generated 60-second, 26.78 MB local fixture
with four AAC tracks and three subtitle tracks:

| Packet validation | Median wall time |
| --- | ---: |
| Old per-track scanner | 1.173 seconds |
| Combined scanner | 0.827 seconds |

This is 1.42x throughput / 29.5% less time **for packet validation only**, not the
whole job. Files and packet evidence passed verification; fixture hashes unchanged.
Cold-cache NAS and full-library throughput have not been measured. No promise of
months-to-days total speedup follows from this local benchmark.

Additional HEVC frame-reader test (60-second generated fixture): two/four decoder
threads were faster, but raw side-data reports differed. Threading changes are NOT
enabled; decoder equivalence needs further qualification. GPU decode and combining
full decode/frame passes are likewise not enabled by this release.

Local automated regression: 416 tests run, 3 skipped, no failures. Generated-media
end-to-end smoke covers six trial encodes, selection, full output validation and
unchanged source hash. Mock CPU encoders/quality floors in that tiny smoke exercise
orchestration only; they do not certify production visual quality.

Benchmark tools: `tools/benchmark_packet_validation.py` and
`tools/benchmark_frame_threads.py`. All generated test assets are on drive E, not Y.

## Build / deploy

```sh
sudo docker build -f /mnt/FR4G/Apps/muxmender/app-build-20260918-v24/deploy/truenas/Dockerfile.app -t muxmender-app:20260918-v24 /mnt/FR4G/Apps/muxmender/app-build-20260918-v24
```

After active jobs finish, use image tag `20260918-v24` in the existing app. Keep
mounts, UID/GID, GPU assignments, ports and environment unchanged. No new variable
is required. Staging does not build/deploy an image, resume the queue, modify the
running workers or delete media. Existing jobs keep using their loaded old code.
