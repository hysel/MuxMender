# RTX 5050 GPU validation experiment

Run on the user's TrueNAS host using the existing MuxMender app image, in a
separate container limited to two CPUs and 2 GiB RAM. No network/library mounts,
no application restart and no permanent Docker access granted to the SSH user.

`tools/benchmark_gpu_decode.py` generated a 30-second 1280x720 SDR HEVC fixture.
Three alternating-order CPU/CUDA runs decoded and downloaded frames, then emitted
per-frame checksums. All 720 frames had identical pixel hashes and timing in all
six runs; the generated source's SHA-256 remained unchanged.

| Path | Median seconds |
| --- | ---: |
| Two-thread CPU decode and frame checksums | 2.206651 |
| CUDA decode, download and frame checksums | 1.950686 |

The CUDA path took **11.6% less time** in this narrow test. This is not a
whole-validation/whole-job speedup and cannot be added to the separate 27.6%
local full-validation result. The latter compares different reader strategies
on another fixture, machine and scope.

**Decision: keep production GPU validation disabled.** The modest measured gain
does not justify removing or substituting existing safety checks without more
evidence. Required future qualification: corrupt/truncated-stream error behavior,
10-bit/HDR/side-data handling, audio decode coverage, representative longer files,
and encoder/decoder contention with Plex. Software fallback must be explicit in
reports; a fallback must never turn a failed validation into a false pass.

The full-validation GPU-independent improvements in v24/v25 remain enabled.
v26 adds per-stage job timing and separate GPU compute/encode/decode telemetry
so the next measurements can identify the actual production bottleneck.
