# Optional GPU frame reader

This directory contains a GPU reader only when the release includes its completed
qualification. Without it, MuxMender uses its existing CPU reader.

A qualified bundle includes the executable, matching full-file comparison and
damaged-input evidence, its hardware/driver binding, the pinned FFmpeg and NVIDIA
header source archives, the applied patch and license notices. Those files are
retained here to make the binary reproducible and satisfy source/license access.

This reader speeds up frame inspection. It does not waive picture-quality,
metadata, corruption, copied-track or verified-replacement checks. A GPU or driver
outside the recorded qualification keeps CPU inspection; the video is not skipped
because of that backend choice.
