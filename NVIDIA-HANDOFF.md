# NVIDIA validation and main-repository handoff

Integration update: the user authorized consolidation, pushing, and merging into main.
The remote workflow UI changes from 32e46c3 were integrated with the tested NVIDIA
code and preserved control-room design. Five additional scripts/modules were
folded into existing entry points; see STANDALONE.md. The combined suite passes
157 tests, and the control-room DOM checks and six live NVENC fixtures pass.

This is the current summary; older experiment logs and chronological notes are
historical evidence, not the current acceptance state.

## Final regression results (2026-09-06)

- Updated full-file pipeline passed end to end on a retained 35.786-second DV
  reference: 857 frames/RPUs, exact non-video packets, metadata, six seek points,
  full decode, source stat unchanged, and 52.56% sample-container reduction.
  Video-only output contained exactly one movie file. This was a bounded
  regression, not another 92-minute movie encode or new user playback review.
  `reports/nvidia-final-e2e/dv-full-20260906-163337-a486db42/validation.json`
- Generated 60/300-second sparse AND empty subtitle tests passed for ordered DV
  finalization: tracks, frame timing, metadata, seeking and decode. Peak observed
  final-mux memory was 36.2/90.6 MiB; encoder peaks were below 198 MiB.
  `reports/staged-mux-stress-20260906-162850-7d153c66/validation.json`
- 126 unit tests passed after the final code changes. Compilation checks passed.
  `reports/handoff-nvidia/unit-tests.log`
- Two earlier end-to-end attempts correctly rejected an offset lost while
  muxing raw video. The final sample timestamp-materialization fix passed without
  relaxing validation tolerance. Failed reports remain as evidence.

## Approved full-movie size reductions

Decimal units; these totals count the two approved movies, not short samples.

| Movie | Original GB | Output GB | Reduction GB | Reduction |
|---|---:|---:|---:|---:|
| Commando | 9.262 | 6.766 | 2.496 | 26.95% |
| 65 (ordered remux) | 17.424 | 11.505 | 5.919 | 33.97% |
| Total | 26.686 | 18.271 | 8.415 | 31.53% |

Total reduction: **8,415.28 MB / 8.415280 GB / 0.008415280 TB (31.53%)**.
The 65 original backup still occupies disk space. These are output reductions,
not a claim that retaining both versions saves physical disk space.

## Validated playback

- RTX 5050, driver 616.64, Windows, Python 3.13.15, FFmpeg/FFprobe 9.0.1.
- Runtime-generated HEVC and AV1 encodes passed at SDR 8-bit and PQ 10-bit,
  including 4K. Listed encoders alone were not treated as hardware validation.
- Full Commando SDR HEVC: user approved picture and synchronization; 26.95%
  reduction. Original audio/subtitle packets and frame timing were verified.
- American Sniper HDR10 HEVC and AV1 samples: user approved Sony TV and PC tests.
- Full 65 Profile 8.1: initial mux failed seeking/TV playback. Corrected remux
  passed Chrome and Sony TV seeking, TV Dolby Vision and sync, then playback
  and seeking from the Y library. Final reduction: 33.97%.

No identical visual-quality claim, universal NVIDIA certification, or hardware
decode certification. The normal optimizer's AMD-only DV gate remains intact.
The separate experimental NVIDIA route is explicitly opt-in.

## Important implementation findings

Video packet timestamps can be correct while physical track ordering is broken.
The failed 65 output had more than 41 seconds of video without audio after a
seek. Startup-only checks missed this. Finite interleave flushing also failed
some positions with sparse subtitles. The repaired output preserves video packet
bytes/timestamps and original audio/subtitles, with no further lossy encoding.

The explicit NVIDIA DV path now materializes injected HEVC into a timestamped
video-only MKV, then combines that video with original tracks. Its ordered mux
uses zero interleave delta. Seek checks require all audio/video tracks within a
bounded packet window at six positions. This remains separate from ordinary
optimizer defaults. Generated sparse/empty-track stress tests cover 60 and 300
seconds, not unlimited-duration memory safety on every possible input.

Sample muxing also needs timestamp materialization before applying a nonzero
starting offset; `-copyts` alone cannot fix undefined raw-HEVC timestamps.

## Product changes already implemented

- Stationary dashboard progress bars; no moving/indeterminate bars.
- Original resolution/color preservation and no automatic quality reduction to
  force savings. Reject equal/larger conversions even at zero minimum savings.
- Run totals in decimal MB/GB/TB and weighted percent. Output size reduction is
  distinct from actual disk space reclaimed while originals/intermediates remain.
- Clean generated names (title/year or show/episode identity); no automatic
  renaming of original media. Existing destination collisions are skipped.
- Matching artwork copied with clean basenames, never overwriting existing art.
- Optional `--video-only-folder`: omit artwork and external subtitles at every
  depth, keep embedded tracks and originals, retain working files separately.
  It does not delete existing destination extras; use a fresh folder.

## Consolidation and pending work

Four obsolete one-off browser/capture/interleave scripts were archived under
`reports/handoff-nvidia/historical-diagnostics.zip` and removed from the project
root. Their reusable sparse/empty-track checks are in the self-contained
`staged_mux_stress.py`. Shared mux/size logic is consolidated in mux_integrity.py. Generated fixtures
and ordinary retained verification live in validate_nvidia.py; retained DV
verification lives in dv_full_file.py. Hardware-specific and UI modules remain
separate where they have distinct responsibilities.

- Optional metadata enrichment for BOTH Plex and generated-file tags is planned,
  not implemented. Default off, fill missing fields, preserve user edits; resolve
  ambiguous identity/provider matches before writes. No installation implied.
- Optional sample/.nfo cleanup is planned, not implemented. Preview exact paths
  and savings first; require approval for deletions. Never infer sample status
  solely from short duration. Preserve main media, subtitles and artwork unless
  an explicit, narrower user instruction authorizes otherwise.
- Preserve CLI/module compatibility when consolidating; do not create more
  one-off scripts. Native AMD/D3D11 components were not validated on this NVIDIA
  machine. Do not discard them merely because they were unused here.

## Current media and safety state

- Y:/Movies/Commando (1985)/Commando (1985).mkv is the approved HEVC conversion.
  Its original was deleted only after explicit one-time approval. Matching JPG
  was renamed; .nfo removed under separate approval. Local full copies removed.
- Y:/Movies/65 (2023)/65 (2023).mkv is the approved repaired DV output.
  `65 (2023).mkv.original-backup` preserves the original. Do not delete it.
- C:/MuxMender-Plex/65 (2023).mkv retains the approved local repaired copy.
- Obsolete generated media was cleaned only with authorization; reports remain.
  Historical report paths may intentionally point to removed intermediates.
- Git consolidation/push/merge operations were explicitly authorized for this
  integration. Future work must still respect user permission boundaries.
  Do not install/update software, open/reload VS Code, or delete other Y media.

## Evidence entry points

- `reports/nvidia-validation-20260905-195603-7925d098/validation.json`
- `reports/nvidia-full-commando-20260905-204727-7a3ce153/full-verification-210222-c6a7fdec/validation.json`
- `reports/nvidia-dv-full-65/dv-full-20260906-085358-cbfa0f53/ordered-remux-20260906-103728/validation.json`
- `reports/65-repaired-y-publication.json`
- `reports/nvidia-final-e2e/` (includes failed attempts; consult final evidence)
- `reports/handoff-nvidia/` (unit logs, source snapshot, evidence manifest)

## Handoff method

Workspace: `C:\Users\itama\Desktop\MuxMender-NVIDIA-365d793c`.
Local HEAD file identifies `testing/nvidia-validation`; expected starting baseline
was fc7fdda. This is not a clean/committed-state assertion.

The earlier handoff archive predates consolidation. Use the integrated Git
source for continued development. Preserve unrelated local work when updating
another checkout. Reports/media/portable binaries stay outside version control.
The user-approved control-room design is preserved in dashboard_ui.py, shared
by dashboard.py and the Web UI history page; DASHBOARD.md records this requirement.
