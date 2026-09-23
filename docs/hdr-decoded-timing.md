# Preserve the picture clock, not the packet list

A generated HDR10 regression on an older NVIDIA representative exposed a muxing
problem, not a GPU encoding failure. A cut GOP contained 62 decoded pictures but
the container's timestamp export included additional pre-roll/non-output packets.
The fresh encode still contained the correct 62 pictures. Assigning the packet
timestamp list to them shifted their presentation times during HDR finalization.

The shared finalizer now writes its timestamp list from the original decoded
frame evidence. It preserves the start offset and variable gaps, rejects missing
or non-increasing timestamps, and does not change duration tolerances. Full frame,
metadata, copied-track and decode checks still have to pass after packaging.
This same finalizer serves the CLI and app; there is no GPU-name exception.

## Verified evidence

- The original regression reproduced the duration change after finalization.
- With the fix, the generated 1080p HDR10 fixture passed three scene comparisons
  and full output validation on the Pascal representative: 76.69% smaller output.
- Original fixture checksum unchanged. This proves this generated workflow, not
  every real HDR source or every older NVIDIA model.
- Linux regression suite: 699 tests, five environment-dependent skips, including
  a STOP-path check proving no full encode or publication after interruption.
- Complete validation benchmark on a separate generated 30-second fixture,
  three alternating rounds: median 1.247 seconds legacy versus 0.865 seconds
  current, a 30.6% validation-time reduction. Not total conversion throughput.
- Cleanup of the diagnosed failed generated run removed 12 disposable artifacts
  (60,957,608 bytes), retained source checksum and compact reports, and a second
  preview found zero remaining disposable artifacts.

## Reporting

An incomplete codec evaluation is not evidence that a source is already
efficient. The development observer now counts those outcomes separately from
legitimate quality/size keeps and marks the finished research record for attention.

Full-length Dolby Vision/HDR10+ adapter qualification also passed at CQ24:
81,246 frames, 69.80% smaller output, 6,568 seconds elapsed. Timing, dynamic
metadata and copied tracks passed preservation checks. The 120-second fixture
passed with 71.33% reduction. Both remain separate experimental copies; these
results do not authorize production replacement or blanket guardrail removal.
