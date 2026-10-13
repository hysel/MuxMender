# Faster input decoding for NVIDIA encoding

Development evidence, 12 October 2026. Not enabled by default or deployed.

A production AV1 SDR encode used NVENC but only two CPU decoder threads, with
zero GPU-decoder utilization. A generated 20-second 1080p AV1 fixture compared
two CPU threads, four CPU threads, and CUDA decoding feeding identical NVENC
settings. Three interleaved rounds measured median encoding times of 3.681,
3.676 and 1.417 seconds respectively. More CPU threads did not help this fixture;
CUDA was about 2.6 times faster. Decoded pixels and timestamps matched exactly.

The shared workflow then passed generated output preservation and quality checks
with both input paths: 480 frames, identical 26,326,824-byte output sizes, mean
VMAF 99.872274 and fifth percentile 99.403433 against unchanged 94/90 floors.
Shared encode calls measured 4.149 seconds on CPU and 1.895 seconds on CUDA.
These are encoding timings, not a projected whole-job speedup.

Qualification used FFmpeg 9.0.2. The first shared attempt found that an older
exported VMAF library lacked built-in models; no thresholds were lowered. The
successful rerun used FFmpeg, FFprobe and VMAF extracted as data from the qualified
v61 image. Generated media was removed after the checks; reports remain.

The opt-in CLI flag `--research-gpu-encode-input` exercises the shared route for
progressive AV1 8-bit SDR input and NVIDIA AV1/HEVC encoders. Frames download back
to the existing filter chain, leaving resizing and color handling in place.
Unsupported research inputs fail explicitly; ordinary jobs are unchanged.

Before automatic activation: test representative real-file input, missing color
metadata, audio-mux recovery, damaged-input behavior, and a full safe-copy run.
Keep all source integrity, preservation, quality, savings and publication checks.

## First full-file comparison

`tools/qualify_full_encode_input.py` runs paired full-file experiments through
the same automatic workflow. Both modes use identical AV1 settings and unchanged
94/90 quality floors, metadata, frame timing, copied-track and size checks.
The source mount must be read-only. Fresh production-idle evidence is required
throughout processing; missing evidence or queued production work stops research.
Full copies remain research-only, even when every check passes.

The first real-file pair completed: CPU decoding took 6,916.52 seconds overall;
CUDA decoding took 6,390.70 seconds, a 7.6% reduction in elapsed time. Both passed
preservation and full quality checks over 145,943 frames, with identical mean
98.2724315 and fifth-percentile 96.052395 scores. The source hash was unchanged.
Neither met the size requirement: about 350 MB saved versus a required 1 GB.
They remain unapproved research copies, not successful replacements.

Full scoring alone took roughly 74 minutes. The next bounded experiment compares
two/four metric threads and CPU/CUDA decoding using the same existing pair,
frames, model and score thresholds. Every per-frame metric must match within
1e-6 before considering a faster path. No frame subsampling is introduced.
Automatic activation and the next build remain on hold until representative
full-file and failure-path results have been reviewed.

The eight-round bounded comparison passed over 720 frames per round. Median
seconds were 19.75 (CPU decode, two scoring workers), 10.03 (CPU decode, four),
20.05 (CUDA decode, two) and 10.23 (CUDA decode, four). Every per-frame metric
matched exactly; both input hashes remained unchanged. Peak measured child RSS
was below 0.5 GB. This supports increasing scoring workers, not using CUDA for
this scoring path. A full-file four-worker re-score is now running against the
previously validated source/copy hashes and unchanged quality floors. This is
still research evidence; the production resource policy has not changed.

The subsequent full-file four-worker scoring run passed in 2,233.81 seconds
(37.2 minutes), compared with roughly 74 minutes for two workers. All 145,943
frames were scored; mean and fifth-percentile deltas were both zero, and source
and candidate hashes were unchanged. AV1 scoring-only eligibility is now
integrated behind the shared resource budget and user ceiling, not deployed.
GPU decoding was not enabled for scoring because the bounded comparison showed
no improvement. Decoder and HDR-reader eligibility remain separate.
