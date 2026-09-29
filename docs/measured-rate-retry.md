# Better decisions without relaxing quality

Automatic mode can now spend one of its existing retry slots on a HEVC rate-control check. This addresses cases where changing CQ alone does little because the encoder's selected rate limit constrains the result.

The retry runs only after a candidate has passed preservation checks but failed measured quality. It keeps that candidate's settings and changes its peak-rate ceiling. The ceiling is calculated as six times the source file's average bitrate, bounded between 20 and 1,000 Mbps. This is a trial heuristic—not a measured source peak, target output bitrate, or promise of smaller files. An explicit user-selected ceiling takes precedence.

Before reading a video for that retry, the app tests the candidate settings on 64 generated frames at the source dimensions and pixel format. A runtime failure remains a processing error, not an “already efficient” decision. A working probe only permits the trial: normal quality, resolution, color/HDR, timing, track and size checks still apply. No card model is assumed to support a setting.

The CLI and app use the same processing engine. Baseline settings remain unchanged. UHQ and explicit lookahead/multipass are not enabled by default. The retry uses the existing adaptive budget, and there is no automatic CPU fallback.

## Less repeated work

When an earlier candidate exposes a difficult scene, later candidates check that scene's quality first. Evidence from another codec is used only to order checks; it never rejects an untested codec. All required scenes must still pass before a full conversion. Exact saved decisions remain reusable only under the matching source identity, settings and evaluation policy. This policy update lets newly submitted folders reconsider older decisions; it does not change or resume an existing queue.

## Clearer results

Results distinguish insufficient savings, measured quality failure, a mix of both, and processing errors. These are results for the tested settings, not proof that a file is optimal. Sample reductions are estimates; only verified replacements count toward library space saved.

## Qualification limits

The large-file research showed that a higher explicit HEVC ceiling can improve measured quality, but no tested candidate for those research cases met every requirement. This change does not approve those files or fix their separate static-HDR metadata defect. The latter still requires its own production-ready repair and full-file validation.

Generated-frame probes and regression tests verify the new control flow. They do not certify every NVIDIA generation, driver, media format, or playback device. A higher permitted peak can also change the encoder's chosen bitstream level, so it is not a blanket playback-compatibility guarantee. Existing per-file checks and playback policy remain authoritative.

The September 24 development snapshot passed 868 regression tests, including
retry-budget enforcement, failed-probe/non-cacheable outcomes, full validation
after a sample winner, source protection, and rendered UI label tests. Generated
64-frame HEVC probes passed on the TrueNAS RTX 5050 at 1920×1080/8-bit with a
20 Mbps ceiling and 3840×2076/10-bit with a 200 Mbps ceiling. These verify
initialization, not source HDR metadata preservation or full-file quality. No
production deployment or end-to-end performance improvement is claimed here.
