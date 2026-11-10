# Changelog

For published versions, read the
[release notes on GitHub](https://github.com/hysel/MuxMender/releases).
The version notes below describe the changes included in each package.

## 20261110-v72

- Recover older AVI samples through a lossless working copy when a direct
  copy cannot reproduce the original pictures. Check the pictures, timing and
  copied tracks before using that sample.
- Preserve display metadata carried by SDR video instead of rejecting it by
  category. Every value must still match the original.
- Preserve changing HDR mastering metadata through HEVC. Recheck alternatives
  when the smaller candidate cannot preserve the complete source metadata.
- Recover copied subtitle and secondary-video tracks when their original
  timestamp order cannot pass through the first muxing attempt.
- Keep the original declared playback length when a remux recalculates it.
  Complete picture and copied-track validation remains required.
- Verify AAC packet-duration representation changes against the original audio
  instead of reporting them as changed audio.
- Avoid repeated work when checking audio tracks with missing packet durations.
- Recover a malformed MPEG-2 initialization header in a verified working copy,
  keeping the original and compressed media bytes intact.
- Let matching 10-bit SDR quality checks use GPU scoring after a complete
  CPU/GPU trial confirms matching scores and a speed gain. CPU fallback and
  near-threshold confirmation remain in place.
- Stream native Dolby Vision comparisons into GPU scoring when a matching
  CPU trial confirms the scores and a speed gain. Share the source render
  between its self-check and candidate check; both still cover every frame.
- Let a long Dolby Vision video qualify its own GPU scorer with a bounded
  comparison when no earlier scene matches. Keep that trial separate from
  complete video validation.
- Stop a failed CPU quality check promptly instead of repeating it as a GPU
  fallback attempt.
- Use the shared audio checks for native Dolby Vision conversions. Preserve
  existing source-audio issues with a visible warning, and reuse complete audio
  checks only while their source and output proofs still match.
- Pause or cancel all parts of a streaming comparison together, and reserve
  resources for its renderers as well as its scorer before starting work.
- Allow bounded shader startup time during hardware-renderer discovery,
  respecting a shorter user-selected task limit.
- Show the specific error when a worker fails before creating its result.
- Keep generated hard links registered for cleanup after metadata restoration.

Quality, savings and replacement checks remain in place.

## 20261106-v71

- Check smaller encoding candidates first. Once a fully validated option wins,
  avoid expensive checks on larger alternatives that cannot improve the choice.
  Close alternatives, retries and final output validation still get their checks.
- Feed supported NVIDIA HDR encodes with more CPU decoding capacity when the
  server has room. Respect CPU limits and other applications; use a smaller
  worker pool when it fits instead of waiting unnecessarily.
- Measure active GPU scoring time separately from resource waits and pauses.
  Explain why CPU scoring was retained and use complete frame evidence when a
  container omitted its scan-type tag.
- Avoid repeating an oversized HDR reference-cache attempt for every scene.
- Preserve verified source color interpretation in temporary container read
  views, fixing false color-range failures while keeping real conflicts blocked.
- Keep throughput measurements separate for different decoder worker counts
  and hardware routes. Report the allocation actually used after a fallback.

Your quality and savings targets, audio, subtitles, timing and replacement
checks are unchanged. No new mounts, environment variables or host scripts are
required. Existing resource settings are kept after the update.

## 20261105-v70

- Let supported NVIDIA quality checks use GPU scoring after confirming matching
  CPU/GPU scores and a speed gain. Confirm near-threshold results on CPU and
  retain CPU fallback when acceleration is unavailable or unhelpful.
- Make automatic resource use aware of running stages and available CPU, RAM
  and GPU engines, rather than keeping a fixed number of videos busy.
- Reuse pixel-verified lossless HDR comparison references within a job and
  remove temporary reference files during normal cleanup.
- Improve sample-based size forecasts and recover dashboard records from brief
  Windows file-sharing conflicts.

## 20261030-v69

- Add an on-demand time breakdown and encoding-choice comparison inside each
  video's Details. Distinguish measured work, waiting, partial sample coverage
  and missing older evidence without adding report scans to live polling.

- Compare up to two faster NVIDIA presets for longer videos after finding a
  passing candidate. Prefer a measured speed gain only within a bounded size
  tradeoff; keep the selected quality, savings and full-file validation checks.
- Measure native encoding time separately from queue waits and GPU-sharing
  pauses, so scheduling delays do not decide which preset appears faster.

- Avoid an extra GPU scheduling delay after allowing validation to catch up.
  Keep GPU-sharing pauses, pressure backoff and concurrency limits in place.
- Reuse GPU workload measurements when only a generated metric report filename
  changes; retain separate measurements for different processing settings.

- Restart the last cancelled queue from the UI, keeping its previous settings
  and history. Review eligible videos before starting fresh attempts; completed
  jobs and individually removed items stay untouched.
- Include cancelled jobs in individual retries and retry-only folder selection.
  Retrying a selected video does not expire its original file-age selection.

## 20261029-v68

- Verify complete video packet clocks on the output time base when a transport
  stream and Matroska report duration differently. Require exact clock conversion
  and the full decoded-frame audit; copied audio and subtitle checks stay strict.
- Let CPU-only validation use available CPU, RAM and storage capacity while GPU
  encoding is busy. Keep the two-validator ceiling, sustained-headroom checks
  and separate GPU admission limits.
- Replace the ambiguous progress label **Measuring…** with **Working…** or
  **Waiting**. Explain what the current check does and show its elapsed time.
  Keep unknown percentages separate from measured progress.
- When resource details are delayed, report active jobs as running instead of
  incorrectly saying they are waiting for a worker.

## 20261029-v67

- Let a waiting inspection use a GPU reader verified by another job while it
  was waiting. Readers already running finish normally; quality checks and
  shared-server resource limits are unchanged.
- Read complete Matroska containers with stray trailing bytes through a verified
  temporary copy when those bytes cause reader errors. Keep the source unchanged,
  report the recovery, and require the usual full validation before replacement.
- Read a sample's missing pixel format from all its decoded pictures instead of
  failing on an incomplete sample header. The pictures must match the source.
- Preserve original audio packet durations in temporary Matroska samples when
  muxing rounds them differently. Repeat packet, timing, picture and metadata
  checks; do not relax timing tolerances or alter the source.

## 20261028-v66

- Set up supported GPU inspection automatically inside the app. Compare a full
  CPU/GPU reference and damaged-input controls once, save verified results in
  private output storage, and reuse matching checks after restarts and updates.
  No host qualification script, extra mount or new environment setting is needed.
  Show the outcome in job details; keep full CPU inspection when a check fails.

- Allow two different GPU stages to share spare capacity after sustained healthy
  resource readings. Keep the two-stage limit, resource backoff and GPU sharing
  controls; mixed workloads do not count as measured throughput improvements.
- Explain when an updated GPU frame reader needs fresh qualification instead of
  silently falling back to lengthy CPU inspection. Existing reader integrity,
  picture quality and preservation checks remain required.
- Check source video timing before sample encoding and expensive preflight
  work. Report confirmed source timestamp conflicts as **Source timing issue —
  original kept**, separately from processing failures.
- Recover AVI samples whose copied audio clock rounds differently from the
  video clock. Restore only the temporary sample's timestamps from matching
  original packets, then repeat normal picture, timing and copied-track checks.
  Original media and quality requirements are unchanged.

## 20261028-v65

- Before HEVC encoding, read HDR10+ metadata through the HEVC stream and check
  its coverage against all decoded source frames. Reuse that extraction within the
  job and remove its temporary data when the job finishes.
- Check original video timestamps near the end before a full SDR encode. If
  decoded pictures and original packets confirm a timing conflict, keep the
  original and explain that a separate repair is needed. Complete output
  validation remains required for files that proceed.
- Preserve audio/video alignment when cutting MPEG-4 AVI samples whose tracks
  use different timestamp clocks. Copied packets, decoded pictures and timing
  must still match the source; quality and savings checks are unchanged.
- Recover AVI sample timing through short, independently verified lossless
  samples when stream copying changes display timing. Check original pictures,
  timestamps and copied audio, and estimate savings from original compressed
  bytes rather than temporary sample sizes.
- Explain a copied sample's track-timing mismatch separately from missing or
  ambiguous source packets.
- Keep slow standalone-job discovery outside the queue lock so it does not
  block dashboard reads, pause or cancellation while scanning saved reports.
- Show cancelled attempts as **Cancelled**, rather than **Needs attention**,
  and keep them out of the attention filter.

## 20261027-v64

### Folder selection

- Filter files by **Older than** as well as **Created within the last**, using
  minutes, hours, days or weeks. Preview shows the matching files before you add
  them to the queue. Existing queued requests are unchanged.

## 20261015-v63

### Conversion fixes

- Keep original audio tracks with existing decoding issues unchanged and show a
  warning in results and replacement records. Copied packets and timing must
  still pass preservation checks; unreadable tracks and newly introduced errors
  still stop replacement.
- Preserve HDR10+ and changing light-level metadata when making AV1 copies of
  HEVC HDR sources. The usual quality, timing and size checks still decide
  whether a copy can be used.
- Find the installed Dolby Vision tool instead of referring to an old local
  development path.
- Identify conflicting source video timestamps before encoder trials. Results
  explain why timing repair is needed instead of reporting repeated encoder
  errors. Variable frame rates remain supported.

### Updates are easier to understand

- Open **Release notes** beside the version at the bottom of the dashboard to
  see what changed in that version.
- Stable updates now require published release notes for the matching image
  version. The release process checks for notes before uploading an image and
  publishes them before promoting it to stable.
- The installation and update guides explain where to read the notes before
  updating through TrueNAS or Docker.

### Before updating

Keep your existing folders and app settings. Review the published release notes
for any additional steps when the next release is available.

### Known limitation

TrueNAS 25.10.7 custom-app image updates do not display a release-notes link in
their update dialog. Read the new version's notes on GitHub before updating.
