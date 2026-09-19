# Episode B: cross-encoder comparison (not production selection)

User approved comparison of the alternative encoders discussed, including CPU.
`tools/compare_encoders.py` measures the same existing difficult reference clip
for x265, SVT-AV1, x264, VP9, VVC, NVENC HEVC and NVENC AV1, two settings each.
It never starts a full conversion, replaces source files, or installs software.

The reference is the approximately 10-second third scene from Episode B's adaptive
run: `/output/auto-20260916-194937-ea9455ee/reference-2.mkv`.
Inputs longer than 20 seconds are rejected. Output must be a disjoint directory.

It reports whole-clip bytes, encode wall time, VMAF mean/p5, preservation and decode
checks. CRF/CQ/QP numbers are not equivalent between encoders. These two-point
trials are not exhaustive rate-distortion curves or evidence of codec superiority.
Passing this one scene does not qualify a full episode or certify Plex support.

All children inherit a four-logical-CPU affinity cap on Linux; encode and metric
stages have 10-minute limits and the comparison has a 45-minute budget checked
between operations and during streamed stages. A blocking probe can delay budget
enforcement until its own timeout. These are resource-bounded results, not maximum
hardware throughput. No parallel encodes or CPU fallback in production auto mode.

Unavailable encoders are recorded explicitly. VVC muxing, decoding or 8-bit
preservation may be unsupported even if the encoder is listed; that is a failed
test, not a silent bit-depth change or permission to install new dependencies.
Original geometry, frame timing, color and copied audio/subtitle checks remain.

Recipe option references: https://ffmpeg.org/ffmpeg-codecs.html

Launch once in the TrueNAS administrator shell:

```bash
sudo docker exec -d --user 3005:3005 ix-muxmender-muxmender-1 \
  python3 -B /output/adaptive-code-20260916/compare_encoders.py \
  --reference /output/auto-20260916-194937-ea9455ee/reference-2.mkv \
  --output-dir /output/codec-comparisons --execute
```

Per-setting results: `codec-comparisons/encoder-comparison-*/comparison.json`.
The normal dashboard displays the tracked job and terminal log. Retained partial
outputs are not approved test results. No new image build or restart is required.
