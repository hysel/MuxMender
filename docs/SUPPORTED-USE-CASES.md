# What MuxMender can do

Reviewed 28 September 2026 against the v41 working tree and recorded runtime
results. Implemented does not mean every input is qualified. Deployment is
separate from code changes; older research notes describe their own checkpoints.

## Everyday workflows

- Inspect a video without converting it, test excerpts, or encode a full copy.
- Select a video or mixed-format folder. Include subfolders by default or choose
  one level. Filter recent files by filesystem creation age when available.
- Compare eligible settings automatically or restrict allowed output codecs.
- Keep a separate copy, or explicitly request replacement after validation and
  destination verification. Replacement permanently removes the old original.
- Keep the original when quality or actual full-output savings are insufficient.
- Use history and retries to revisit failures without treating changed sources
  as unchanged files. Selection is not continuous folder watching.
- Use the TrueNAS UI or the shared standalone automatic workflow.

## Media routes

| Case | Scope |
| --- | --- |
| SDR AVC/H.264 and existing HEVC | HEVC/AV1 candidates, subject to measured quality and savings |
| H.264 output | An allowed candidate/fallback, not mandatory or universally suitable |
| MKV, MP4, AVI and other readable containers | Source-driven admission; container recognition alone is not qualification |
| Legacy MPEG-4 Part 2 and previously ripped MPEG-2/DVD video | Timing/color inspection and conditional encoder support; no automatic deinterlacing |
| HDR10/PQ | Preservation routes with full-output checks |
| AV1 HDR content-light repair | Tested constant source metadata restoration; not permission to invent values |
| Dolby Vision Profile 8.1, including HDR10+ combinations | Integrated NVIDIA HEVC route; known metadata failure under investigation |
| Dolby Vision Profile 5 and Profile 7 MEL/FEL | Shared routes with per-file qualification before publication; FEL requires native enhancement-picture evidence as well as fallback checks |
| HLG and unusual HDR/pixel-format combinations | No broad qualification claim; runtime support and complete evidence remain required |
| Unusual dimensions, aspect ratios, short clips, variable timing and rotation | Source-driven handling with checks; selected generated and real-file evidence, not universal certification |
| Interlacing | Conditional on preserved cadence/field order and hardware capability |

Resolution is unchanged by default. Upscaling, frame interpolation, disc ripping,
DRM bypass and downloading media are not the normal library-optimization app.
Historical experiments and legacy standalone tools are not equivalent to the app.

Audio, subtitles, chapters, language labels, dispositions, artwork and additional
video tracks have preservation checks where applicable. AAC priming may require
MP4 output. Not every conversion becomes MKV. No automatic audio dropping is
authorized; missing metadata must be established from evidence, not invented.

## Hardware and operation

Phase 1 targets NVIDIA. Generation hints order trials; actual capability probes
decide eligibility. Older GPUs are not assumed to support AV1. AMD/Intel code and
historical tests remain, but current qualification work is deferred. There is no
standard automatic CPU fallback, driver installer or multi-machine scheduler.
Parallel jobs and shared-host throttling exist; heavy validation scheduling has
a known wait-timeout issue in v41.

## Feedback, savings and cleanup

The UI reports stages, progress, sizes, percentage/GB reductions, history and
activity categories, with CSV export. Lifetime savings count verified replacements,
not retained test copies. ZFS snapshots can still occupy space.

New requests default to size-aware savings: the smaller of 25% or 1 GB, with a
100 MB minimum. Fixed targets remain available. Actual final size and requested
quality floors must pass; quality scores are not percentages of perceived quality.

The shared finalizer removes eligible owned intermediates while retaining logs,
receipts and requested deliverables. Active/uncertain jobs, interrupted publication
and forced shutdowns can require recovery; cleanup is not a blind folder sweep.
See [cleanup policy](post-task-cleanup.md).

## Known v41 failures under investigation

- TrueHD source decoding errors: source damage versus decoder compatibility is
  not yet resolved. No silent track removal.
- AV1/MP4 duplicate decode timestamps: structural failures repeat across quality
  settings; do not misreport them as insufficient savings.
- Heavy validation admission timeout: waiting for another job is not bad media.
- Combined DV/HDR10+ static metadata mismatch: requires source/output diagnosis,
  not disabling preservation checks.

See [tested formats](TESTED-FORMATS.md) for historical evidence. Earlier claims
that all automatic Dolby Vision routes are disabled are superseded by this inventory.
