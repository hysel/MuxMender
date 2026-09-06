# Generic NVIDIA validation handoff

This checklist is capability-based, not tied to an RTX 5050 or any model name.
NVIDIA execution is still pending on the second Windows machine. AMD playback
success does not establish NVIDIA support, quality, performance or HDR fidelity.

## Before starting

- Obtain the approved `testing/nvidia-validation` snapshot. Confirm it includes
  this checklist, `audio_validation.py`, and the local Web UI before testing.
- Keep original libraries read-only where possible. Use fresh local output
  folders; never delete, overwrite, move or rename source media.
- Run `./setup-windows.ps1` for audit only. Installation needs separate consent;
  do not update drivers automatically or reinstall working drivers by default.
- Record GPU model(s), driver version, OS, Python and FFmpeg versions. Record
  `ffmpeg -encoders` and encoder help for `hevc_nvenc` and `av1_nvenc` when listed.
  Encoder presence is not proof that a GPU/driver can execute that encoder.
- With no encoding jobs active, run `python -B -m unittest discover -s tests -q`.

## Test sequence

1. Start `python webui.py` (explicit `--ffmpeg` / `--ffprobe` paths if needed).
   Use the standalone CLI/UI; VS Code is not a runtime requirement.
2. Scan a known SDR H.264 file read-only. Filter to eligible previews. Select
   NVIDIA explicitly and HEVC, then approve a short separate-output preview.
3. Confirm the recorded encoder is NVENC, exact dimensions and bit depth remain,
   copied tracks validate, output fully decodes and savings meet the chosen
   threshold. Review visual quality and A/V sync; don't treat savings as quality.
4. Test AV1 separately only if the build lists it. Unsupported execution must
   fail clearly and retain artifacts, never silently use CPU or another vendor.
5. Test auto selection separately. On multi-GPU machines record which vendor was
   selected; do not assume auto selects NVIDIA or a particular adapter.
6. Test queued cancellation and interrupted-job recovery with short generated
   fixtures, not source modification. Partial outputs must remain; restarts must
   never resume unapproved work. Keep one encoding job active at a time.
7. After preview review, explicitly approve one full episode. Keep validation
   reports, actual source/output sizes, timing, audio/subtitle results, GPU/driver
   details and playback feedback. Full revalidation reads may take minutes.

## Validation acceptance

- Missing initial H.264 DTS is accepted only with bounded reordering evidence
  and decoded PTS checks. Missing PTS and unexplained gaps remain blocked.
- Audio comparisons retain per-track order, payload hashes, PTS and side data.
  Duration rounding needs full decoded sample-count and clock evidence.
- No scaling by default. No automatic CPU fallback or dependency installation.
- HDR/Dolby Vision stay on their separate reviewed routes. The ordinary UI is
  SDR H.264 only; never use the AMD-specific DV route as a generic NVENC path.
- Mark unsupported capabilities as unsupported, not passed or silently skipped.
  A pass on one adapter does not imply a pass on every NVIDIA generation.

## Return to this machine

Share the run/validation reports and logs, relevant tool/driver versions and
playback observations. Redact private paths if sharing outside this workspace;
never include Plex tokens or credentials. Do not delete test outputs without
the user's approval. Intel and TrueNAS validation remain separate pending work.
