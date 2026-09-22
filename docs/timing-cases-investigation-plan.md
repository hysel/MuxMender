# Investigation plan: no release or source replacement

## UI first

- Savings is the first dashboard panel, followed by always-visible resource
  readings. Resource settings alone are collapsible.
- CPU, available RAM, GPU compute/encode/decode and free VRAM are separately
  labelled. Missing readings are unavailable, never falsely zero.
- Queue waiting messages use the actual admission reason, including standalone
  work reported active. This does not change admission or repair stale state.
- Named processing steps and current-check percentages remain; 100% of a check
  is not presented as completion of the entire conversion.

## Timing case A: establish the exact reference window

1. Probe source keyframes/PTS around the failing 477.72-second seek. Record
   preceding/following keyframes, source timebase, starting DTS/PTS and frame rate.
2. Compare the existing reference's first/last decoded frame and audio/subtitle
   timestamps to that source interval. Confirm the same content via decoded-frame
   evidence; do not infer preroll solely from the container duration.
3. Reproduce extraction with a generated long-GOP fixture. Test explicit
   keyframe-aligned selection or decode-trimmed metric windows without changing
   the source or re-encoding the reference used as quality ground truth.
4. Choose a deliberate recorded window. References/candidates must cover exactly
   the same frames and time interval; sample bytes and savings estimates must
   refer to equivalent content. Keep full-file validation independent.
5. Test long GOPs, fractional rates, nonzero starts, sparse subtitle tracks,
   variable timing and near-end seeks. Then retry the real sample as a safe copy.

The proposed boundary allowance was withdrawn. The original duration guard
remains. Do not deploy a relaxed bound as a substitute for this investigation.

## Timing case C: isolate the timestamp rewrite

1. Trace matching DTS-HD MA payload hashes from source to reference, encoded mux
   and any HDR-finalization remux. Identify the first stage introducing the 3 ms
   change, retaining exact commands, timebases and packet durations.
2. Compare source/reference/candidate audio cadence, PTS-DTS relationships,
   cumulative drift and audio-to-video offsets across the entire sample.
3. Test a timestamp-preserving remux in isolated copies. Prefer eliminating the
   timestamp rewrite over widening acceptance thresholds.
4. Only if the rewrite is unavoidable and demonstrated to be bounded, propose a
   documented codec/container-specific tolerance for user review. The existing
   local 5 ms prototype has been REMOVED. The original 2 ms check is restored.
   Any future tolerance proposal needs evidence and explicit review first.
5. Re-run all scene quality/preservation/decode checks, followed by full safe-copy
   validation if eligible. No replacement based only on identical audio hashes.

## Delivery gate

Report source facts, reproduction, exact correction and residual risks before
claiming either issue fixed. No new app image, live hotpatch, queue restart or
media replacement during this investigation. Obtain approval before packaging
any future timing policy or changing its acceptance rules.
