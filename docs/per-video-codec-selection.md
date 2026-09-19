# Per-video measured codec selection

Implemented: `codec_selection.select_candidate()` and the read-only CLI
`muxmender-select-codec REPORT.json --minimum-savings-percent 10`.

The policy selects HEVC or AV1 by the smallest aggregate measured output, only
after explicit runtime, target-playback, quality, preservation and decode checks.
It requires at least three matching reference samples for the same source identity.
Compare identical clips and preserve resolution, aspect ratio, frame rate, color,
audio and subtitles. Use representative scenes across the video, not just its intro.
Different codecs' CQ numbers are not equivalent-quality measurements.

## Fast keep-original screening

The first pass encodes the three short reference clips with each supported GPU
setting and compares their combined bytes. If they cannot meet the configured
savings threshold, expensive VMAF, copied-track and full-decode checks for that
candidate are skipped. This is rejection-only screening: size alone never
approves a conversion. Candidates that can save space still need all quality,
preservation and decode checks; one confirmed failing scene ends the remaining
quality checks for that setting. Adaptive search remains bounded and GPU-only.

The UI reports **Already efficient for current settings: short tests found no
worthwhile size reduction within the quality limits. Original retained.** This
means no acceptable candidate was found among the tested settings, not that the
file has a mathematically optimal size. File size, bitrate and codec alone are
not sufficient evidence. Encoding/validation errors instead report an incomplete
evaluation and are not cached as an efficiency decision.

Completed efficiency decisions are retained in request history, so the same
unchanged file and selected policy skip future testing by default. Changing the
codec, hardware selector, quality or minimum savings re-evaluates these decisions;
explicit recheck/retry also overrides them. After changing physical GPU hardware,
drivers or encoder builds behind an unchanged selector, use explicit recheck.
Existing successful conversions and explicit user keep decisions remain protected.

Reference VMAF self-checks are deferred until a candidate passes the size screen.
They must meet the requested quality floors, rather than a fixed VMAF 98 cutoff:
identical videos can score below 98. Scores are never normalized to 100 and
conversion quality thresholds are not relaxed.

Each trial stores codec, encoder and exact settings. Hardware/vendor does not
determine the winner. Missing/failed checks exclude a trial. If no eligible trial
saves at least the configured threshold, keep the original. Reported savings are
sample estimates, not promises for a full episode. HDR/DV is deferred to specialized
evaluation rather than silently losing metadata.

## Integrated opt-in workflow

`muxmender-auto` now generates trials and feeds their evidence into the selector.
It processes one video per invocation and is dry-run by default:

```sh
muxmender-auto /media/episode.mkv --output-dir /output --hardware nvidia
```

After confirming HEVC/AV1 playback on the intended clients:

```sh
muxmender-auto /media/episode.mkv --output-dir /output --hardware nvidia \
  --playback-verified-codecs hevc av1 --execute --encode-best
```

Without `--encode-best`, execution stops after trials and selection. This explicit
workflow does not change the older main CLI `--codec auto` HEVC default.

Current scope is progressive 8-bit 4:2:0 BT.709 SDR with known range/aspect ratio
and one video track. Unknown metadata, HDR/DV, interlaced/repeated frames and
unexpected geometry are rejected; no resizing or automatic tone mapping occurs.
AMD, NVIDIA and Intel candidates must pass a runtime encoder probe. There is no
automatic CPU fallback and no automatic software installation.

Three stream-copy reference clips near 15%, 50%, and 85% of the video are tested.
Default requested length is 10 seconds each (keyframe-aligned clips can be longer,
bounded to twice the requested length). Videos shorter than six sample lengths
require shorter explicit `--seconds`. Sampling is distributed, not scene-aware;
it cannot guarantee quality in every scene. Default balanced/compact presets
produce up to 12 trials per GPU. `--qualities transparent balanced compact` can
expand the bounded search. The winner is the smallest passing tested setting,
not a globally optimal encoder setting.

FFmpeg must include libvmaf. Each sample must meet mean VMAF >=95 and fifth
percentile >=90 (configurable screening thresholds, not transparency claims).
Incomplete/nonfinite scores, missing frames, changed dimensions/SAR/timing/color,
changed track metadata, changed copied packet bytes/timestamps, and decode errors
all disqualify a candidate. Certain benign mux differences, such as missing AAC
packet duration metadata, are conservatively rejected rather than waived.

The full winner is encoded with the same settings to a unique output path,
then checked for full decoded-frame geometry/timing, stream metadata, copied
audio/subtitle payloads and timing, chapters, A/V decoding, actual savings, and
unchanged source SHA256. VMAF is measured on trial scenes, not every full-file
frame. Full outputs below the savings threshold remain rejected candidates.
Passing outputs still require Plex playback review. `--playback-verified-codecs`
is the operator's prior compatibility declaration, not an automatic Plex check.

Terminal and dashboard job records show execution stages. Plan, trial evidence,
selection, VMAF reports and final status live in the separate output root.
Create `STOP` inside the run directory to interrupt at the next guarded stage;
metadata/frame probes are timeout-bounded and may finish before noticing STOP.
All intermediate media is retained; no automatic cleanup is implemented.

No file writes or deletion are performed by this selector. An `encode_copy`
decision requires full-output validation before publication. Original replacement
is never authorized by codec selection and still needs explicit user approval.

Verification: unit tests cover gating and selection; `tools/smoke_auto_optimize.py`
exercises six real generated-media CPU encodes (test-only GPU substitution), VMAF,
selection and full-copy validation with unchanged source hashes. Relaxed smoke
quality thresholds test plumbing, not real-media quality. The integrated path
still requires real NVIDIA/AMD/Intel qualification on target hardware.

Quality metric reference: https://ffmpeg.org/ffmpeg-filters.html#libvmaf
