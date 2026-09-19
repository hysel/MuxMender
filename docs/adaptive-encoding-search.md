# Bounded adaptive encoding search (first implementation)

Enable standalone mode with `--adaptive`; a rebuilt resident app can enable it
with `MUXMENDER_ADAPTIVE=true`. Default remains off during initial validation.

1. Probe the source and runtime-test permitted GPU encoders.
2. Test the existing balanced/compact presets on the shared three scenes.
3. If none qualifies, rank supported NVIDIA encoders by their best baseline
   weakest-scene fifth-percentile quality score.
4. Try CQ 23, 22, 24, 25 with p7 for each ranked NVENC encoder. Test its historically
   hardest scene first. A failed scene rejects that candidate immediately.
5. Validate all remaining scenes for a candidate that survives screening. Only
   complete, matched, quality/preservation/decode-passing evidence can qualify.
6. Stop at the first qualifying refinement or the extra-trial budget (default 8;
   configurable cap 1-12, currently at most eight available refinement recipes).
7. With `--encode-best`, make and validate a separate full copy. Otherwise report
   selection only. Actual full-file savings must still meet the minimum.

Thresholds are not reduced automatically. Default requirements remain VMAF mean
95, fifth percentile 90, and at least 10% aggregate sample savings. Partial scene
results cannot qualify, and skipped scenes are explicitly recorded. Search steps
and stop reason are recorded in `adaptive-search.json` and `trials.json`.

This is a bounded measured search, not an exhaustive optimizer or a guarantee of
transparent quality or savings. It retains the SDR-only eligibility boundary.
AMD/Intel still use their existing baseline trials; adaptive parameter refinement
is currently NVENC-only. No driver installs or media replacement are performed.

CPU fallback is **not implemented/enabled by this change**: exhausted searches
record `not_run_requires_explicit_opt_in`. A separate opt-in CPU search remains
follow-up work. Do not interpret that status as an attempted CPU encode.

Validation stages now publish frame-timing and copied-track labels instead of
leaving an old encoding-100% label during long full-file checks.

Initial real-media target: Series A S01E06 Episode B, which failed the first
fixed-preset comparison. Outcomes are pending execution on the TrueNAS GPU.
