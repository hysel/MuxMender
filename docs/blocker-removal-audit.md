# Blocker-removal audit

These changes are tested in the research environment, not deployed. No production
queue was changed and no library original was replaced during this effort.

## Current follow-up status

Phase 1 is NVIDIA-only by user decision. Physical AMD/Intel qualification is
deferred, not a prerequisite for that phase. The explicit FEL separate-copy
research command is described in [FEL research](fel-research.md); it does not
enable automatic FEL replacement or claim reconstructed-picture qualification.

The sections below retain earlier checkpoints. They are not the latest
qualification matrix. See [remaining-blockers progress](remaining-blockers-progress.md)
for the subsequent source-driven implementation and generated runtime evidence:

- Short/subsecond sources, display rotation, AAC priming/container fallback,
  extra tracks, unfamiliar side data and interlaced H.264 fallback have shared
  implementation and bounded generated tests.
- Profile 5 now passes the ordinary CLI with native-render quality, GPU-renderer
  discovery, open-GOP boundary recovery and complete-file validation. Extra-track
  and variable-timing tests also passed. This new path remains separate-copy-only.
- Profile 7 MEL preserves the complete enhancement payload and RPU sequence;
  both native-DV and HDR10 fallback quality views passed generated full-file tests.
- FEL has a separate-copy research encoder and a working portable native-render
  comparison: all 246 sample frames passed the metric at 55.55% size reduction.
  A no-intermediate-media streaming comparison matched those scores exactly;
  the complete explicit CLI path also passed with further resource bounds. Native quality
  integration into automatic selection passed the ordinary CLI full-copy test; the production
  FFmpeg filter alone does not reconstruct FEL.
- Physical AMD/Intel and older-NVIDIA qualification is not inferred from the
  RTX 5050 tests. The newer source-driven routes try compiled selected backends
  and retain per-candidate runtime errors rather than declaring a vendor incapable.

The latest remote suite passed 845 tests. Whole-source reuse and the pinned
runtime's isolated dependency setup passed all-frame qualification. Docker
dependency wiring passed an isolated non-root image build and automatic FEL,
Profile 5 and MEL separate-copy tests. The image has not been deployed.
The current-image reader exposed a broken-excerpt case; complete-source
fallback passed the end-to-end test without weakening checks. The verified
246-frame sample was 55.56% smaller, with the enhancement layer and metadata
preserved. Mixed MEL/FEL inventories now select native FEL reconstruction
instead of a blanket rejection; the synthetic 246-frame alternating-metadata
runtime test passed. Missing or unknown inventory values remain errors.
The current evidence and retained limits are consolidated in
[the qualification checkpoint](qualification-handoff.md). NVIDIA Phase 1
investigation and separate-copy qualification are complete; physical AMD/Intel
work is explicitly deferred. Deployment and source replacement are not authorized.

The app-result audit found and removed a remaining MKV-only acceptance check.
The app and publisher now share the container contract: MP4/MOV outputs need
matching explicit container evidence, alongside the existing owned-path, hash
and full-validation requirements. An explicitly copy-only workflow no longer
launches a publication child just to fail qualification; its validated output
is retained with a clear replacement-qualification explanation. Tests cover
valid native outputs, missing/mismatched evidence and no-publication behavior.

## Earlier checkpoint: what the evidence supported

| Area | Implementation and verification |
| --- | --- |
| Savings | Shared exact-byte policy across selection, full-file checks and publication. Size-aware targets range from 100 MB to 1 GB; fixed percentages remain available. One-byte boundary tests prevent rounding from changing acceptance. |
| Dolby Vision 8.1 | Shared NVIDIA HEVC adapter reuses sample and full-file services. Real full-length evidence and generated offset, variable-rate and secondary-video tests passed. RPU, HDR metadata, timing and copied tracks remain independently checked. |
| Artwork and extra video | Primary selection excludes attached pictures. Other moving tracks are copied and packet-verified. A generated unlabelled JPEG cover survived MP4-to-MKV attachment conversion. |
| Missing metadata | Consistent decoded labels may recover missing container labels. Conflicts are not guessed away. A fresh complete HEVC inventory can contradict a stale DV declaration, but sampled absence cannot. Generated HDR and SDR stale-label cases passed the full automatic workflow. |
| Source formats | Syntactically valid pixel formats reach runtime capability trials instead of a historical format allowlist. Output preservation remains mandatory. |
| Long GOPs | Complete keyframe-pair selection can include a preceding group covering the requested scene. Expanded packet and decoded-picture proof passed a generated multi-video HDR test with zero timestamp tolerance. |
| Shared packaging | The remote test snapshot matched 214 compared local Python/JavaScript files and the package manifest. The complete Linux regression suite passed 736 tests without skips. |

Generated size reductions are workflow evidence, not predicted savings for a
library. Test copies do not count as reclaimed disk space. The detailed evidence
and qualification limits are in [source-driven admission](source-driven-admission.md).

## Earlier checkpoint: qualification limits at that time

- Interlaced HEVC and AV1 failed initialization on the tested NVIDIA card. H.264
  preserved all 25 generated frames, field order and timestamps, but that alone
  does not prove acceptable quality or savings. Automatic deinterlacing is not
  enabled, and a user's codec choices must not be silently changed.
- A Profile 5 frame rendered on the NVIDIA GPU after process-local graphics-driver
  selection. This is not a complete Profile 5 re-encoding or quality qualification.
- A complete inspected stream labelled Profile 7 contained no RPU or enhancement
  layer. That supports stale-label recovery for that stream, not disposal of real
  Profile 7 enhancement data in another file.
- Four inputs failed repeat container-header inspection. Repairing damaged input
  is different from removing an arbitrary format gate.

## Earlier checkpoint: inventory and retained restrictions

The two-way inventory contains the same 214 Python/JavaScript files locally and
remotely, with no missing files and matching hashes. The package manifest also
matches. The latest remote suite passed 736 tests with no skips, and the worktree
passes `git diff --check`.

The routing review confirms that the ordinary HDR route cannot consume genuine
Dolby Vision and discard its metadata. The qualified adapter requires NVIDIA
HEVC, single-layer Profile 8.1 and the user's HEVC playback selection. A later
follow-up adds an explicit peak-rate ceiling consistently to sample, preflight
and full encoding. A generated 540-frame variable-rate multi-track test passed
full validation at 1 Mbps; 739 regression tests passed. Per-file quality and
preservation remain mandatory. These are explicit limits, not a
claim that all Dolby Vision or hardware paths now work.

Other retained checks include unreadable input, missing or conflicting color and
timing evidence after recovery, unsupported extra track types, unhandled rotation
or other geometry side data, actual encoder initialization failures, and output
quality, savings, decode, track and timing failures. Missing dependencies and
insufficient resources are reported rather than treated as successful conversion.
The software does not fabricate preservation evidence to admit these cases.

## Earlier checkpoint: handoff (superseded by the active follow-up)

That narrower checkpoint preceded the current blocker-removal goal. It is not
completion evidence for the active follow-up. See the current status above and
the chronological progress report for subsequently implemented Profile 5/MEL,
interlaced H.264 and other-vendor routing work. FEL reconstruction and physical
other-vendor qualification remain incomplete; they are not silently waived.

Deployment, image publication and git publication still require approval. The
existing TrueNAS portal setting also needs its host-port correction during that
deployment; it cannot be repaired by a Docker image alone. See the
[deployment checklist](../deploy/truenas/NEXT-RELEASE.md). Original media and the
production queue were not modified by this research effort.
