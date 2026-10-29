# Changelog

For published versions, read the
[release notes on GitHub](https://github.com/hysel/MuxMender/releases).
The version notes below describe the changes included in each package.

## Unreleased

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
