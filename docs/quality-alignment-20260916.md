# Quality alignment regression and correction

The first NVIDIA auto pilot completed safely with no full-file encode. Every
candidate's third sample failed VMAF although metadata, decoded frame counts,
geometry and timing (within 2 ms), and copied track checks passed.

Investigation on the same saved clips reproduced mean VMAF **64.694847** (5th
percentile zero). Matching frames at ordinal 40 looked closely aligned, and a
reference-versus-itself run scored mean **99.638499**. Encoded and reference
timestamps differed by 1 ms on some frames (e.g. 1.668 vs 1.669 seconds).

The old `setpts=PTS-STARTPTS` metric graph retained those rounding differences.
FFmpeg framesync could select the previous reference frame. A common ordinal
clock applied ONLY in the metric graph produced mean **96.374028**, minimum
**89.071572**, and frame 40 **99.840591** instead of zero for HEVC balanced.
No encoder settings, source, or output video were changed in this experiment.

Correction: validate decoded frame count, geometry, and original timing first;
then map both metric inputs to the same clock using verified frame order. This
does not relax output timing checks, modify the files, resize, or change FPS.
Each reference also gets an identity self-check before any candidate selection;
mean <98 or 5th percentile <95 aborts as a measurement failure.

Previous pilot reports remain unchanged. New scores are stored separately and
must not be treated as an already completed full-file conversion. Quality floors
remain mean 95 / 5th percentile 90. Sampling remains a quality screen, not a
guarantee for every scene or client.

Reference: https://ffmpeg.org/ffmpeg-filters.html#libvmaf
