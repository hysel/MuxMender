# Bounded adaptive encoding search (first implementation)

Enable standalone mode with `--adaptive`. The media-workspace UI enables it
when quality is automatic; explicitly selected quality presets remain fixed.

1. Probe the source and runtime-test permitted GPU encoders.
2. Test the existing balanced/compact presets on the shared three scenes.
3. If none qualifies, rank supported NVIDIA encoders by their best baseline
   weakest-scene fifth-percentile quality score.
4. Try CQ 23, 22, 24, 25, 20, 18 with p7 for each ranked NVENC encoder. The last
   two provide higher-quality alternatives when baseline quality is insufficient. Test its historically
   hardest scene first. A failed scene rejects that candidate immediately.
5. Validate all remaining scenes for a candidate that survives screening. Only
   complete, matched, quality/preservation/decode-passing evidence can qualify.
6. Stop at the first qualifying refinement or the extra-trial budget (default 8;
   configurable cap 1-12).
7. With `--encode-best`, make and validate a separate full copy. Otherwise report
   selection only. Actual full-file savings must still meet the minimum.

Thresholds are not reduced automatically. Default requirements remain VMAF mean
90, fifth percentile 90, and at least 10% aggregate sample savings. Partial scene
results cannot qualify, and skipped scenes are explicitly recorded. Search steps
and stop reason are recorded in `adaptive-search.json` and `trials.json`.

This is a bounded measured search, not an exhaustive optimizer or a guarantee of
transparent quality or savings. It retains the SDR-only eligibility boundary.
Runtime-tested AMD/Intel encoders can additionally try their transparent preset
once if it was not already tested. This uses the same hardest-scene-first checks
and budget. No unverified encoder or CPU fallback is introduced.

CPU fallback is **not implemented/enabled by this change**: exhausted searches
record `not_run_requires_explicit_opt_in`. A separate opt-in CPU search remains
follow-up work. Do not interpret that status as an attempted CPU encode.

Validation stages now publish frame-timing and copied-track labels instead of
leaving an old encoding-100% label during long full-file checks.

Initial real-media target: Series A S01E06 Episode B, which failed the first
fixed-preset comparison. Outcomes are pending execution on the TrueNAS GPU.
