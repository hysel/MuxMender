# Episode B: higher-quality short-clip comparison

The seven-encoder comparison completed with no tested setting meeting both
quality and size requirements. Inspection of matched frame 29 showed a dark,
grainy scene and apparent texture smoothing in x265 CRF 21. This single-frame
observation does not establish whole-clip perceptual quality or a metric fault.

The opt-in `--profile higher-quality-cpu` compares x265 slow CRF 17/18/19
and SVT-AV1 preset 6 CRF 12/16/20 using the same difficult reference clip.
Acceptance thresholds remain VMAF mean 95 and fifth percentile 90. These
CRF values are not equivalent across encoders. No full-video qualification,
replacement or deletion is performed. CPU affinity remains four logical CPUs;
each subprocess has a ten-minute timeout and the comparison a 45-minute budget.

Prepared on TrueNAS as a separate script; requires an administrator to launch:

```sh
sudo docker exec -d --user 3005:3005 ix-muxmender-muxmender-1 \
  python3 -B /output/adaptive-code-20260916/compare_encoders_hq.py \
  --reference /output/auto-20260916-194937-ea9455ee/reference-2.mkv \
  --output-dir /output/codec-comparisons \
  --profile higher-quality-cpu --execute
```

The tracked job title includes `higher-quality-cpu`. Results are written in a
new unique `encoder-comparison-*` directory. Original files remain unchanged.
