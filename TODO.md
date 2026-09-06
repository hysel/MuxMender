# MuxMender to-do

## Safety and product requirements

- Standalone script first; VS Code is only an optional development interface.
- Never delete, overwrite, move, or rename original media. Cleanup requires
  explicit approval for the particular generated files; no automatic cleanup.
- Preserve exact resolution by default. Dolby Vision-to-PQ conversion is opt-in.
- Do not restart/reload/open VS Code windows without explicit permission.
- Ask before Git commands, including push and merge.

## Current AMD full-episode test — check on return

- [ ] Review completion and validation of the full Star Trek episode run.
  At the last check on 2026-09-04 at 22:42 local time, it was still encoding:
  5.79% overall (approximately 7.23% of video encoding), no failure in the log tail.
  This is not a completed or verified full-episode result.
  - Log: `reports/run-20260904-222603-65c86ac2.log`
  - Run directory: `test-output/stream-full-20260904-222606-dbe340ac/`
  - Live state: `status.json`; final result: `validation.json`.
  - Expected final video: `episode-hevc.mkv`.
  - Python PID at launch: 49072 (recheck before using; PIDs can be reused).
  - Original: `\\truenas\Media\TV\Star Trek - Strange New Worlds\Season 4\Star Trek Strange New Worlds S04E05 Level-Five Transporter Accident 2160p ATV WEB-DL DD5 1 DV HEVC-NTb.mkv`.
- [ ] Confirm final exit status, complete frame/timestamp matching, original
  audio/subtitle packet equality, chapters, dimensions, HDR tags, decode success,
  source size/mtime, actual savings, and intended-player playback.
- [ ] If it fails, diagnose retained logs/partials before retrying. Do not
  automatically restart the job, switch to CPU, or remove any files.

## TrueNAS / Linux deployment — requested for later

- [ ] Confirm TrueNAS edition/version, CPU, RAM, and installed GPU(s); the
  proposed RTX 5050 is one possible test device, not a deployment requirement.
- [ ] Package the standalone script in an app/container using locally mounted
  datasets: source read-only, separate output dataset writable. Do not use SMB
  for media already hosted on the same TrueNAS machine.
- [ ] Implement and validate a Linux-compatible Dolby Vision color backend;
  the current Windows/Direct3D 11 helper cannot run unchanged in Linux.
- [ ] Validate NVIDIA driver/container GPU exposure and FFmpeg compatibility
  through supported TrueNAS configuration; installation must remain opt-in.
- [ ] Test file permissions, no-clobber behavior on ZFS/datasets, disk-reserve
  checks, cancellation, and recovery. Do not assume hard links work across datasets.
- [ ] Profile CPU decoding, color conversion, GPU/CPU transfers, FFV1 pipe
  overhead, encoding, and local storage before promising throughput gains.

## NVIDIA behavior — test later on real hardware

- [ ] Make NVIDIA detection and encoding capability-driven across GPU models
  and generations, not tied to RTX 5050 or any fixed model name. Detect each
  available GPU and validate the selected device with runtime preflights;
  advertised encoder availability alone is not validation.
- [ ] Build a representative hardware matrix covering older/newer generations,
  integrated or discrete GPU configurations where applicable, and multiple-GPU
  systems. RTX 5050 is an optional test case, not the baseline requirement.
- [ ] Check encode and decode capabilities separately for each device, including
  H.264/HEVC/AV1, bit depth, pixel formats, and supported dimensions. Do not
  assume every NVIDIA GPU supports NVENC, AV1, or 10-bit encoding. Clearly report
  unsupported paths without silently changing resolution, color, or quality policy.
- [ ] Test SDR, HDR, and explicit DV-to-PQ paths, exact resolution, colors,
  audio/subtitles/chapters, quality versus savings, throughput, and memory.
- [ ] Test missing drivers/tools, encoder failure, explicit CPU fallback,
  stalls, cancellation, long runs, and preservation of originals/failed outputs.
- [ ] Validate the relevant Windows and TrueNAS/Linux environments separately.

## Intel behavior — test later on real hardware

- [ ] Identify target Intel iGPU/Arc generation; test QSV detection and actual
  HEVC/AV1 encode/decode support without assuming all generations are equivalent.
- [ ] Apply the same SDR/HDR/DV, quality, stream preservation, and safety
  checks as NVIDIA; include relevant Windows/Linux driver and device access.
- [ ] Test dependency prompts, CPU fallback consent, stalls, cancellation,
  memory, throughput and long-run stability.

## Fidelity-first Dolby Vision preservation

- [x] User reviewed the full AMD HDR/PQ episode on 2026-09-05 and reported
  that it looks good. This validates that viewing test, not DV preservation.
- [x] Add profile-aware preservation assessment to standalone scan output and
  JSON reports, with regression tests. This is planning, not a new encoder path.
- [x] Prototype short HEVC profile 8.1 samples with unchanged color processing,
  dimensions and frame timeline, extracting and preserving frame-aligned RPU.
  Candidate detection is not proof that a file or encoder supports this flow.
  AMD 192-frame test passed metadata/content and structural checks on 2026-09-05;
  see DOLBY-PRESERVATION.md for qualifications. It is larger than its reference,
  so not a space-saving result. General DV re-encoding remains blocked.
- [x] User visually approved the 30-second scene sample and confirmed Dolby
  Vision picture mode on a Sony Android TV (2026-09-05). Sample:
  `DV-Preservation-Knight-S01E02-30s-Scene-20260905-092939.mkv`.
  Video payload saving for that scene: 26.5%; not a full-episode prediction.
- [x] Review additional 30-second sections near 12 and 22 minutes; do not
  assume an opening logo or one scene establishes whole-episode quality.
  Both passed automated checks and were published to test-output on 2026-09-05.
  Filenames contain `at-12min` and `at-22min`. Video payload: 12-minute sample
  43.7% smaller; 22-minute sample 25.5% larger. User confirmed playback review.
  Reports/log: `reports/dv-scenes-20260905-101630-261332b0/`.
  Do not promote these settings as guaranteed savings or start a full encode
  based only on the smaller scenes; tune and validate quality/size first.
- [ ] Tune representative-scene quality/size and address experimental muxer
  warnings before promoting this prototype into the end-user optimizer.
  QP21/23 trial on the 22-minute scene passed automated checks on 2026-09-05:
  46.26% smaller video payload versus source (previous QP18/20 was 25.5% larger).
  New file contains `22min-Tuned-QP21-23`; user visual/DV playback review pending.
  Defaults remain QP18/20. Do not infer whole-file savings or quality acceptance.
  Report: `reports/dv-tuning-20260905-103347-d9be197a/dv81-20260905-103347-6eaa197d/validation.json`.
- [x] User approved the QP21/23 tuned scene; implement full-file experimental
  Profile 8.1 workflow. 81 tests and an 8-second end-to-end full-file smoke passed.
- [ ] Review full episode launched 2026-09-05 10:46 local, AMD QP21/23:
  `reports/dv-full-20260905-104650-3893eee8/terminal.log` and `status.json`.
  Final `validation.json` and `episode-dolby-vision.mkv` will be in that directory.
  Execution session 57138; not yet a completed/verified episode. Retain originals.
  Publish to Plex only after verification; review actual savings and playback.
- [ ] Check optional dovi_tool availability and present opt-in installation;
  never silently download tools or switch to CPU. Test AMD/NVIDIA/Intel separately.
- [ ] Validate RPU content/count/alignment after muxing, signaling, base-layer
  decode, audio/subtitle packets and chapters; compare difficult scenes and
  actual Dolby Vision playback before allowing full-file optimization.
- [ ] Research a separate profile 5 preservation pipeline for the current
  Star Trek source. Do not inject its original RPU into the rendered PQ output.
- [ ] Preserve enhancement layers; do not silently turn profile 7 into 8.1.
  Unknown or unsupported profiles remain skip/copy-only.
- [ ] Treat quality as the primary acceptance criterion, not maximum savings;
  document that lossy encoding cannot guarantee perceptually identical output.

Research references:

- https://github.com/quietvoid/dovi_tool (RPU extraction/injection and profile modes)
- https://x265.readthedocs.io/en/master/cli.html (Dolby Vision encoder options)

## Follow-up usability/performance tasks

## Approved standalone workflow / Web UI work package

- [x] Reusable read-only library planner with durable per-file results and reasons.
- [x] Localhost Web UI: paths, scans, recommendations, previews, explicit full-file approval, queue and logs (initial SDR H.264 route).
- [x] Serialized jobs, free-space reserves, cooperative cancellation, interrupted-job detection; no silent CPU fallback.
- [x] Windows prerequisite script: detect first, confirm each install; never install drivers automatically.
- [x] Automated security/safety tests and end-user documentation.
- [x] Handle bounded initial H.264 B-frame DTS omissions using matching decoded PTS and regression tests; retain blocks for unexplained gaps and missing PTS.
- [x] Add recommendation/path filtering to large saved scans with stable row identity and filtered pagination.
- [x] Show later validation, playback approval and removed outputs without rewriting earlier failures.
- [x] Prepare generic NVIDIA validation handoff (NVIDIA-HANDOFF.md).
- [ ] Browser visual QA when requested.
- [ ] Continue hardware validation: generic NVIDIA, then Intel and TrueNAS.
- Full episodes may be converted into separate outputs. NEVER delete, overwrite,
  rename, or move original media. Git and driver/install actions still require approval.

- [x] Local read-only dashboard: live progress, stage ETA, persistent job history,
  expandable logs, and automatic tracking of standalone CLI runs. See DASHBOARD.md.

- [ ] Allow the optional MuxMender Output channel to follow an existing
  standalone log without restarting VS Code or the encoder.
- [ ] Accept paths supplied directly in chat for testing; no repeated picker.
- [ ] Improve phase-aware ETA reporting; overall progress reserves 20% for
  copy/validation and must not be mistaken for video encoding percentage.
- [ ] Give Plex test outputs clearer titles; distinguish video-only
  intermediates from final outputs that contain audio/subtitles.
