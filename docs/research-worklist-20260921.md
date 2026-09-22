# Research execution ledger — 2026-09-21

This is a historical experiment log, not a live task list. Later entries can
supersede earlier results. Start with the [plain-language status](STATUS.md)
and [roadmap](TODO.md); keep this page for the detailed evidence.

Authorized: work through this list without step-by-step prompts. Production
queue remains paused; source media and retained production outputs are mounted
read-only in `muxmender-research`. Scratch: `/work/research-20260921-r1`.
No production deployment, source replacement or Git write performed by research.
Implementation, excerpt qualification and full-file qualification are separate.

1. Language case A language: narrow `und`/missing FFprobe stream-tag comparison
   implemented. Actual MKVToolNix inspection confirms both retained tracks have
   explicit `und`, despite FFprobe omitting it. Known-language loss stays rejected.
   36 focused tests pass. Fresh full preservation revalidation running, PID 109.
2. Timing case B average rate: no relaxation implemented. Fresh decoded source and
   retained-output timing comparison running, PID 126. Output directory
   `Timing case B-timing`; this diagnostic does not authorize publication.
3. Artwork case A HEVC cover handling: pending implementation and qualification.
4. Three missing-color sources: pending evidence-based research.
5. Artwork case A AV1 chroma position: pending research.
6. Redundant structurally failing trials: pending implementation.
7. Dolby Vision size/quality: pending qualification; production guard stays on.
8. Combined DV/HDR10+: pending qualification; production guard stays on.
9. Shared-engine regression suite and TrueNAS qualification: pending final run.
10. Faster no-savings screening/history reuse: pending. Efficiency case B predicted
    11.54% but missed 10% on full output; include Efficiency case C and prior Efficiency case A
    comparison. Decisions must remain settings/policy-specific.
11. Four 4:4:4 series 10-bit 4:4:4 sources: pending current-hardware qualification.
12. AV1 case A interrupted validation: pending recovery investigation.
13. Long encode case A full encode stall near 22%: pending investigation.
14. Full-file retries: Timing case A, Timing case C, Savings case A, Artwork case B, MP4 case A, Timing case D, HDR quality case A,
    HDR case B. Existing sample/code fixes are not full-file proof.
15. Historical result reconciliation: pending; preserve history.
16. Recursive final Animation coverage audit: pending; distinguish evaluated,
    deliberately retained, unresolved, stale and never processed.
17. Single-host performance: pending measurements, caching, dynamic concurrency,
    GPU validation/encoding and storage/CPU/RAM capacity recommendations.
    Multi-machine processing explicitly excluded.

Before research: v34, 51 replaced, 27 failed historical records, 202 skipped,
14 pending, zero active; queue manually paused. 23 unique historically failed
files: 8 later replaced, 15 without later replacement; two interrupted files
also later replaced. 42 files have skipped-to-replaced history (overlap exists).

Security setup: passwordless sudo allows only root-owned
`/root/muxmender-research-access`, which executes non-root Python in the fixed
isolated container. No general Docker access. No changes to Plex or Ollama.

## Execution findings (later entries supersede initial statuses)

- Timing case B fresh full decoded comparison passed 112,440 frames, unchanged
  geometry/timing. Source/output rates `89071/3715` and `27021/1127` differ only
  very slightly; output is 26.674% smaller. Implemented narrowly bounded average
  rate compatibility **only after** independent full frame evidence; exact SAR
  and timeline checks remain. Full revalidation exposed a separate missing
  duration on the first AAC initialization packet; not yet fully qualified.
- Language case A fresh frame preservation passed; copied packets exposed a first AAC
  initialization PTS difference. All 201,786 decoded audio frames compared equal
  (PCM bytes and sample counts), maximum timeline delta 0.333ms; both diagnostic
  FFmpeg processes exited zero. The initial packet itself emits no audio frame.
  Added a candidate-specific full PCM SHA256 proof path, not a general packet
  timing tolerance relaxation. End-to-end updated workflow still needs rerun.
- Artwork case A HEVC real sample: 254 frames pass exact HDR metadata/timestamps, copied
  audio/subtitle/cover payloads and complete decode; 79.979% smaller. Research
  output `/work/research-20260921-r2/Artwork case A/hdr10plus-preserve-76956c4dfe94`.
- Artwork case A AV1 first exposed missing chroma siting, then equivalent mastering-display
  fractions (`35400/50000` vs `177/250`). Source-driven siting support and exact
  rational mastering comparison added. Repaired retained sample passed all 254
  frames and decoded pixels are identical before/after signaling repair:
  `/work/research-20260921-r3/Artwork case A-av1/result.json`. Quality not yet approved.
- All three missing-color examples actually contain MPEG-4 Part 2 video, not
  H.264 (even the one named x264). No range guess has been implemented.
- Per-encoder redundant structural-trial suppression implemented; quality,
  packet/decode failure and timeouts are not swept into this suppression.
- Full-output size rejection now precedes costly full validation. It cannot
  authorize publication; viable-sized outputs still require full validation.
  Existing history already reuses full-size rejections for unchanged settings
  and policy; UI labels now describe tested savings rather than ideal format.
- Initial full suite: 562 tests, only missing new-module packaging registration
  failed; registration corrected. Focused AAC/metadata/packaging tests pass.

## Latest qualification checkpoint

- Full suite now passes: 571 tests, 3 skipped. One UI test was updated for the
  more accurate "No worthwhile savings" label; no assertion was removed.
- Language case A updated full preservation validation **passed**, 103,211 video
  frames, 25.439% smaller, 879 seconds in the bounded lab. Includes independent
  complete decoded AAC proof and complete output decode. Prior quality is not
  re-measured by this retained-output test; publication remains unauthorized.
- Fresh Artwork case A HEVC shared encode/finalization/validation **passed**: 254 frames,
  79.979% smaller, HDR common-render VMAF mean 97.477 / p5 96.032. Preservation
  took 34.7 seconds; complete sample qualification with metric self-check took
  307.1 seconds while another CPU validation ran in the 4-vCPU research lab.
- MPEG-4 Part 2 default range: three sampled Visual Object headers per source
  prove absent video_signal_type for all three legacy examples. ISO/IEC 14496-2
  section 6.3.2 defines range zero in this case. Added bounded parser/recovery
  and negative tests; no resolution/name-based assumption. Conversion tests
  remain queued, so this is not yet a quality-qualified fix.
- Animation read-only recursive inventory: 82 current files, 51 receipt-backed
  job replacements, 14 queued, 13 retained decisions (including four blockers),
  three unresolved failures, one stale signature; no inventory read errors.
  Stale file is HDR case A: current 3,967,744,385 bytes versus old
  source records 11,263,387,718 bytes. Separate preservation report indicates
  64.773% reduction, but no matching UI replacement receipt was found yet.
  Do not infer provenance solely from matching size.
- r4 batch PID563: Language case A passed, Timing case B full revalidation running.
- r5 batch PID726: fresh HEVC passed; fresh AV1 then DV CQ28/30/32 qualification.
  Expanded only explicit bounded DV research search; production DV guard stays.
- r7 batch PID1071: three MPEG-4 and four 4:4:4 series 4:4:4 automatic sample trials,
  waits for r4/r5 to finish; no full encode or replacement in this batch.
- r8 batch PID1327: generated CPU/CUDA decode equivalence and complete validation
  benchmarks, waits for r7 to avoid contaminating measurements with other work.
- r9 batch PID1328: ten full-copy qualifications (eight listed Animation files,
  AV1 case A, Long encode case A); waits for r8. Shared engine, adaptive hardware trials,
  mean/p5 90, 10% minimum savings. No source write or publication commands.
  Process exit zero alone is not a conversion pass: inspect each final decision.

## Subsequent findings

- Fresh Artwork case A AV1 shared path also passed: 254 frames, 71.231% smaller, HDR
  common-render VMAF mean 98.102 / p5 96.674. HEVC saved more on this sample;
  AV1 scored slightly higher. Neither result is a full-film qualification.
- Combined DV Profile 8.1/HDR10+ experimental path implemented in the shared
  DV sample module, with HDR10+ extraction/editor/injection and independent
  exact per-decoded-frame comparison. Duplicate JSON metadata keys are retained.
  RPU content/order, tracks, geometry, timestamps and full decode remain checked.
  At 300s: 88.474% video-payload reduction, mean 95.351 / p5 91.135, all checks
  passed. At 900s: 92.359%, mean 94.026 / p5 92.030, all checks passed. These
  are video-payload figures, not measured full-container or library savings.
  1500s qualification still running in r11 (PID2053); r10 PID1538 completed.
- Ordinary DV DV series B CQ28 passed quality but saves only 0.118%; below the 10%
  target. CQ30 saves 29.885%, mean 91.401 / p5 89.796; rejected by quality.
  CQ32 comparison running. CQ29 refinements at 300/900/1500s are queued in r12
  PID2622. Research CQ range is now integer 18..32; production guard unchanged.
- Corrected research sample qualification to require its explicit savings
  floor (10% default), rather than treating any positive video reduction as
  sufficient. Historical CQ28 report's sample_qualified=true is superseded by
  the above below-target assessment, not silently rewritten.
- DV sample timeline validation no longer sorts away decoded-frame reordering;
  static HDR is checked on every frame, not only the first. Negative tests added.
- Timing case B complete decoded audio proof: 219,881 frames, exact PCM/sample
  identity, **zero** presentation-time difference. Its first packet DOES emit
  audio, so the Language case A non-output initializer proof was correctly inapplicable.
  Separate missing-first-duration handling now requires unchanged packet timing
  and complete PCM timeline proof. r14 PID3707 runs the updated complete workflow,
  reusing r4's completed full-frame evidence with input/evidence checksums, not
  repeating frame collection. No automatic production validation cache added.
- Indexed folder history lookups preserve existing decisions: synthetic local
  10,000-job/1,000-lookup check was 1.197s versus 0.00470s including index build.
  This is NOT an encode-speed claim. Failed admission decisions from older
  releases can be retried for non-HDR routes too; successful outputs stay protected.
- UI full-size rejection details now include actual input/output GB, actual
  reduction and target, explicitly saying when full validation was not run.
- Folder browsing now uses shared media extensions instead of a smaller list
  which silently excluded WMV/MPEG/WebM and other supported containers.
- Governor now accounts for CPU allocation saturation inside a capped container;
  an idle host cannot justify adding work to an already saturated CPU quota.
- Latest full regression checkpoint before the last AAC/governor changes:
  575 tests passed, 3 skipped. Final full suite still required.
- Benchmark waiting parent is now PID2623, waiting for r7 and r12 (which follows
  r11); old waiting parents were stopped only after verifying no child had started.
  r9 unstarted full-file snapshot was updated with the latest shared fixes.

## Current execution checkpoint (supersedes older pending notes)

- Timing case B r14 completed full preservation successfully: 112,440 video
  frames, 219,881 identical decoded audio frames with zero timing difference,
  complete output decode and track evidence. Retained output is 26.674% smaller.
  Quality was not rerun by this preservation-only diagnostic; no publication.
- DV series B CQ29 passed three 10-second scenes at 300/900/1500 seconds, with
  video-payload reductions 13.474/17.577/38.925%; VMAF mean/p5 respectively
  92.336/90.862, 93.531/92.549, 92.623/92.095. Combined DV/HDR10+ third scene
  also passed: 89.121% payload reduction, mean 92.142/p5 90.711. Full files
  remain unqualified and production guards remain enabled.
- Full DV research now propagates explicit CQ to both preflight and full
  encode. Preflight requires shared quality evidence as well as savings;
  metadata-only success cannot authorize full work. Decoder stderr is checked.
- r8 isolated generated-fixture benchmarks completed. SD complete validation:
  legacy median 2.511s, current 1.800s, 28.310% lower time. 720p HEVC decode
  and downloaded frame checksums: CPU 1.699s vs CUDA 1.943s, identical pixels
  and timing. This does not justify enabling GPU validation globally or claim
  equivalent gains for 4K/full job throughput. r9 ten full-file tests started.
- Found an additional false-cache risk: FFprobe/FFmpeg could log decode errors
  but exit zero, allowing corrupt references to become size-only 'efficient'
  evidence. SDR frame reader now rejects decoder errors like the HDR reader;
  shared encoder uses -xerror. Reference recovery is tried before declaring
  failure. Existing corrupt-reference r7 4:4:4 series conclusions are invalid,
  explicitly superseded, not silently rewritten.
- MPEG-4 AVI remuxes require generated missing PTS and complete GOP boundaries.
  Recovery verifies exact decoded pictures, contiguous original packet hashes,
  shared timeline shift, and <=2ms container quantization. Including the future
  boundary picture fixes a last-frame B-picture dependency. Long GOP search
  expands within bounded 30-second references, not a fixed five-second gate.
  Both AVI inputs now reach codec trials (r20); Legacy case A exposed decoder
  AVFrame color tags overriding encoder context. Source-proven setparams
  signaling added without pixel conversion; new qualification pending.
- 4:4:4 series source initial ten seconds decode cleanly but mid-file seeks fail,
  even after ordinary stream-copy recovery. r20 continuous-from-start checks
  distinguish source corruption from random-access decoder context. Do not
  classify this as GPU/4:4:4 hardware inability.
- r19 PID7724 completed, r20 PID9201 running. r9 PID1328 started before a
  requested waiting-snapshot update; the assertion correctly prevented any
  mutation of that live snapshot. No production/source changes occurred.

- Timing case A fresh full shared workflow passed, 59.332% smaller, with source
  and output SHA256 recorded. r9 now processing Timing case C. No replacement.
- 4:4:4 series root cause confirmed: original x264 core 146 UUID SEI is absent from
  stream-copy excerpts. FFmpeg's source-derived `-x264_build 146` compatibility
  context makes the previously failing clip decode cleanly. Beginning-to-860s
  source decode also passes (51,549 frames); this is not damaged source or GPU
  incapability. SPS/PPS hashes are constant across that prefix (239 occurrences).
  Added shared decoder_context parser (actual SEI UUID/payload, not names/tags),
  original/reference-only decoder options, packaging and negative tests. Fresh
  four-file adaptive qualification queued in r24 PID11674 after r20.
  FFmpeg implementation: https://raw.githubusercontent.com/FFmpeg/FFmpeg/n8.0/libavcodec/h264_slice.c
  and https://coverage.ffmpeg.org/index.h264dec.c.8820c603e94612cd02689417231bc605.html
- r21 PID10430: adaptive legacy trials then ordinary DV full CQ29, after r20.
  r22 PID11286: combined DV/HDR10+ full CQ30 after r21. Full research now retains
  and compares all dynamic metadata via streaming JSON, injects HDR10+ before
  RPU, keeps source-driven settings and full decode checks. Both paths still
  require full qualification; production guards remain unchanged.
- Governor memory admission now distinguishes host reserve from container
  reserve plus a two-GiB new-job budget. A healthy eight-GiB container is no
  longer permanently blocked by a ten-GiB host reserve. Low host/container
  memory and CPU quota saturation still prevent additional launches.

## Research qualification update (16:20 UTC)

- r21 legacy results: Legacy case A now has eligible AV1 compact samples, 41.967%
  smaller; HEVC balanced also eligible at 38.218%. Legacy case B has
  eligible HEVC compact samples at 14.133%. Legacy case C remains a
  settings-specific size/quality rejection, not a missing-color failure.
- r24 4:4:4 case A passed shared HEVC sample preservation, decode and quality
  checks at 41.860% reduction. Source-derived x264 context is qualified on these
  samples; the other three 4:4:4 series sources and full-file approval remain pending.
- Adaptive NVENC search now explores stronger compression first when size is
  the only measured limitation, retaining all quality/preservation requirements.
  Evaluation policy bumped to source-driven-adaptive-size-quality-2 so earlier
  settings-specific no-savings decisions can be reassessed once. Converted and
  explicit-keep identities remain protected. No production history was changed.
- Native progress reports current-stage percentages even when a caller allocates
  no overall percentage span, and throttles duplicate notifications without
  weakening advancing-frame/timestamp stall detection. Top resource telemetry
  distinguishes host CPU from the app's allocated CPU quota.
- r22 and r26 were updated only while waiting with no started children. Active
  snapshots are immutable. r27 PID19237 queues latest-policy legacy full-copy
  qualification after r24/r22, with originals read-only. r9/r26 full-file work
  continues separately. No production resume, replacement, release or Git writes.

- 4:4:4 case C and 4:4:4 case D also passed shared 4:4:4 series sample checks,
  estimating 40.415% and 43.344% savings respectively. 4:4:4 case E is active.
- Timing case C full encoding finished; the provisional before-HDR-finalization file
  is 3,143,493,036 bytes. Full source HDR metadata inspection is active, so this
  is not a qualified output or a library savings receipt.
- Observed HDR quality FFmpeg automatic pools using 48 threads and ~3.8 GiB RSS
  inside the four-core quota. Shared quality_command now bounds both decoder
  pools and complex-filter workers to two, keeps libvmaf's existing two workers,
  and rejects decode errors. Rendering, frame count and score policy are unchanged.
  r28 PID20263 will compare automatic/bounded pools on identical 24-frame HDR
  inputs after r22/r24; equivalence/performance remain unqualified until it ends.
  r22/r26/r27 were refreshed only while waiting with no active steps.
- Latest complete suite before the final two added regression tests: 593 run,
  three skipped, no failures. New timestamp-detail and explicit-keep coverage
  tests pass in focused runs. Rerun complete suite before final handoff.
- Optional user request sent to raise only research CPU quota from four to eight
  using docker update; no quota change made by the agent. Tests continue at four.

- r24 completed: all four 4:4:4 series inputs passed three-scene shared qualification.
  4:4:4 case E selected HEVC compact at 47.653% sample savings. These are
  not full-file publication approvals.
- Ordinary DV 30-second preflight passed, mean 91.592/p5 90.090, with all required
  preservation and savings evidence. Full source scan started in
  r21/dv-full/dv-full-20260921-163521-c11c823f.
- r28 metric benchmark was advanced safely during low-memory source-scan stages,
  waiting parent20263 terminated before any child, replacement parent22065.
  Four runs completed but equivalence FAILED: automatic repeats match exactly,
  bounded repeats match exactly, cross-mode maximum VMAF delta0.025141 points.
  Full filter-thread bounding also showed no speed benefit. Reverted explicit
  filter-thread limit; do not present r28 as a passed optimization or media error.
  r29 PID22225 now tests decoder-only thread limits against the automatic baseline.
  Unstarted r22/r26/r27 snapshots had filter threading restored before launch.
- Complete local regression suite after progress-detail and keep-audit tests:
  595 tests, three skipped, no failures. Subsequent decoder-only adjustment still
  requires final regression rerun and real metric equivalence evidence.

- r29 decoder-only limit PASSED: all per-frame metric values match exactly across
  automatic/bounded/ bounded/automatic runs (24 HDR frames, input SHA256 unchanged).
  Median wall time14.197s automatic versus13.486s bounded (~5% lower in this
  concurrent-host microbenchmark). Median peak RSS3.463GB versus2.435GB (~30%
  lower). Filter threading is unchanged. This supports decoder-pool bounding,
  not a claimed 5% end-to-end conversion gain. Fifty focused tests passed.

- r27 advanced into the freed low-memory research slot after all r24 tests ended;
  waiting parent19237 stopped before children, replacement parent22436. No change
  to CPU/RAM quotas or production queue. Legacy case C completed the new
  size-directed search: AV1 CQ28 saved20.834% in samples but p5=86.380; CQ27
  saved15.199% but p5=86.489; CQ26 saved8.384%, below10%. Reference self-check
  p5=97.468. Keep under current settings; this is now a measured rejection,
  not missing-color admission failure. Legacy case A full encode started.
- Latest complete suite with decoder-only optimization: 595 tests, three skipped,
  no failures. Ordinary DV research is profile8.1 (HDR10-compatible base layer),
  not blanket qualification of every Dolby Vision profile.

- Timing case C completed source HDR evidence and final packaging/restoration of copied
  track timestamps; now reading every final output frame for comparison. No error
  in those stages. Provisional before-finalization reduction was35.304%.
- Legacy case A completed full AV1 encoding and source-frame evidence, and is now
  validating every output frame. These stages do not yet constitute a pass.

- Legacy case A then failed on the source's final best-effort timestamp `N/A`.
  Source and output each contain116855 frames. Blind `+genpts` would place the
  final picture one frame too late, so it was not used as a fix. Original MPEG-4
  VOL/VOP picture clocks independently align with every known tail timestamp
  (spread below1 microsecond) and every picture type. The recovered final PTS is
  4873.827291667, matching output4873.827 within existing tolerance.
- Added shared source-only MPEG-4 AVI recovery, restricted to exactly one missing
  final timestamp, bounded raw tail, exact decoded picture count/type ordering,
  agreement with all known tail clocks and the full original frame evidence.
  No FPS inference, timing tolerance change, output-driven timestamp or editing
  original evidence. Fresh r32 integration tail contains288 matching pictures;
  earlier independent r30 tail contained170. Six parser/evidence tests and two
  source/codec-boundary regressions added. Complete suite:603 run,3 skipped,pass.
- r31 PID27768 reuses Legacy case A's existing AV1 copy and original frame evidence
  for full preservation/decode requalification, with source and evidence hashes.
  Full validation is still running; no publication authority is implied.
- Legacy case B full HEVC copy finished:744909391 source bytes versus
  691431286 output,7.179142% savings, below10% minimum. Rejected before costly
  full validation. This is an actual full-file size outcome, not a codec blocker.
- Timing case C output-frame validation and ordinary DV full encoding continue.
  r22 combined DV/HDR10+ and r26 remaining full retries remain dependency-queued.
  Production remains paused; no source writes, release, deployment or Git writes.

- r32 fresh shared timing recovery passed comparison of all116855 Legacy case A
  frames. Three additional parser boundary tests brought the local suite to606
  tests,3 platform skips,no failures. r34 ran all three skipped Linux service
  locking/restart/symlink tests and eleven timing tests on TrueNAS:14 passed.
  Initial r34 fixture lacked the ui package; supplied that package and reran
  successfully. This was a test-staging import failure, not a production defect.
- r33 refreshed Animation audit:82 files,inventory_complete=true,no read errors
  or excluded symlinks.51 converted,14 queued,9 retained decisions,4 retained
  blockers,3 unresolved failures,1 stale-history input. Historical failed-source
  cohort remains19,of which10 have current verified production replacements.

- r31 Legacy case A final decode FAILED on an incomplete last AC-3 frame, after full
  video geometry/timing, metadata and copied-track evidence passed. r35 proved
  the complete original audio decode fails on the same incomplete frame. Last
  source/output packet hash matches,1040 bytes versus2560 for preceding complete
  frames. This is source damage, not introduced by video encoding. Do not mark
  the complete file qualified or replace it. Asked whether user wants a separate
  repaired test copy or to retain it as a source-repair blocker; original remains
  untouched either way. No silent audio trimming or quality/timing relaxation.
- Timing case C completed full output-frame inspection and progressed to copied-track
  validation. Ordinary DV full encoding continues; downstream batches still wait
  for their dependencies. No new production results were written.

- User explicitly approved a separate Legacy case A repaired test copy. r36 PID28061
  removes only the diagnosed last1040-byte AC-3 packet from the existing AV1
  research copy. All video packets and remaining audio packets must match; full
  strict audio/video decode and input hashes must pass. This is a research-only
  exception authorized for this test, NOT automatic repair or source replacement.
  Source remains read-only and unchanged; output is isolated under r36/repair.

- r36 repair created successfully. Exactly one diagnosed packet removed:152309
  AC-3 packets before,152308 after. All video packets and all remaining audio
  packets match, and stream metadata checks pass. Strict full audio/video decode
  is running; do not call it fully qualified yet. Separate local test copy copied
  to E:\MuxMender-TestOutputs\Legacy case A-Audio-Repair-20260921-r36\
  Legacy case A-AV1-Audio-Repaired-Test.mkv (1833483439 bytes). Transfer SHA256:
  d776622527ef2dc4d62074845b78c1b85eb1f7239b1672599015f68d3ce9165f.
  Original AVI and pre-repair AV1 copy both retained. No production publication.

- Legacy case A r36 full strict video/audio decode PASSED; final input hashes match,
  repaired output hash matches the local E copy. User reports playback looks good.
  This is an approved repaired test copy, not source-replacement permission.
- Timing case C full shared workflow PASSED at35.302948% reduction. Savings case A
  full HEVC copy saved9.032734%,below10%; retained original,not accepted. Artwork case B is active;13 other full files were still pending at that checkpoint.
- Ordinary DV r21 stopped after final mux with missing process-memory telemetry.
  Reproduced exit race on TrueNAS:98/100 short processes had missing memory fields
  while poll still reported running,then exited normally. Shared memory guard now
  waits at most100ms for exit/rechecks live memory; live unavailable measurements
  and over1GiB still fail closed. Nonzero exit still fails execution. Added tests.
- Retained DV verifier now accepts explicit tool paths and a run-contained output,
  honors requested savings floor, validates seek ordering, and refuses the source
  as its output. r37 PID31470 reused the completed DV encode; ordered remux passed
  in23s and preservation verification is active. Original failed output retained.
  Combined DV/HDR10+ r22 is active on its immutable snapshot; r26 still waiting.

- Phase telemetry now clears old percentage/ETA/detail on a stage transition,
  while retaining explicitly supplied new progress. Two regression tests pass.
- Full HDR frame-audit timeouts now scale with duration, bounded between one and
  24 hours; active snapshots retain their original settings. No validation is
  removed. Latest complete suite:616 tests,3 platform skips,no failures.
- Waiting r26 plan extended with Savings case A and Legacy case B HEVC
  CQ24..27 refinements, unchanged minimum10% savings and VMAF mean/p5>=90.
  Waiting-only parent restarted as31582; nine sequential cases follow r9.
- Experimental DV frame evidence now includes source-derived geometry, SAR,
  pixel format and color signaling per frame. Comparison catches mid-video
  changes rather than checking only stream headers. Older compact evidence
  must be refreshed for this check; current immutable tests do not include it.
  Focused DV suite:13 tests passed, including two new picture-signature tests.

- Additional generated FFprobe fixture confirms real geometry/SAR/color output.
  Retained DV verification refreshes older incomplete frame evidence automatically.
- Corrupt/truncated generated FFV1 fixtures demonstrated FFmpeg can log errors
  and exit zero despite -xerror. Shared native_pipeline.stage strict_decode mode
  checks each diagnostic line (not just exit status or last200 log lines).
  Automatic full decode/AAC PCM and experimental DV final decode enable it.
  Clean fixtures pass; both damaged fixtures fail. No hidden errors found in
  completed r9/r27 decode logs. This fix strengthens evidence, not a format gate.
- Full local suite622 tests passed,3 platform skips. r38 Linux focused suite38
  tests passed. Waiting-only r26 code refreshed; no active snapshot mutated.
- Artwork case B source timing finished; output timing is underway. Ordinary
  DV recovery and combined DV/HDR10+ continue. Duplicate-video-decode avoidance
  remains an unenabled research option until equivalent full evidence is proved.

- r39 strict full audio-only DV decode passed in30.826s; existing full video/audio
  decode continues unchanged as the comparison baseline. Shared finishing logic
  now reuses only the current complete validated video frame audit, then decodes
  every audio track strictly. Missing/full-count mismatch falls back to video/audio.
  Generated clean, corrupt-video, truncated-video, and identical-but-corrupt copied
  audio tests pass. Final local suite625 passed,3 skipped; r40 Linux68 passed.
  Waiting r26 updated after Linux qualification; active snapshots unchanged.
- r41 read-only audit examined retained full-decode logs for all51 production
  replacements:49 clean,2 DTS-HD diagnostics (Audio case A and
  Audio case B). All164079/155393 reference/output audio packet records
  are identical. Current-file SHA256 matches published output in both cases.
  Fresh full audio-only decoding is clean (64.494s and62.579s); old warnings not
  reproduced. No repairs, deletions or production-history changes were made.

- Ordinary NVIDIA DV full recovery PASSED:60773 frames,10.207895% file reduction,
  full RPU semantic digest/static HDR/timeline/track/chapter checks and complete
  audio/video decode. Source unchanged, no publication. Final report:
  r21/dv-full/dv-full-20260921-163521-c11c823f/verification-181729-855f9fc6/validation.json.
  The old snapshot lacked the newly added per-frame picture-signature field; do
  not backfill that claim. Full finishing decode1211s vs strict audio-only30.826s
  on the same copy; shared-host stage comparison, not overall speedup.
- Combined r22 hit its original3600s frame-evidence timeout near93%, source
  unchanged. r42 uses current duration-aware timeout and shared decode reuse.
  Initial retry launcher rejected the harmless python -u flag before opening
  media; corrected, old launcher diagnostics retained, parent now32670. Full
  fresh qualification is active; no production release/queue/source changes.

- Artwork case B complete shared workflow PASSED at76.142695% reduction.
  Its full-decode log contains no hidden diagnostic. r9 advanced to MP4 case A; remaining full tests continue in order. Source unchanged.
- r43 real4K HEVC240-frame ABBA CPU/CUDA checksum comparison PASSED: exact
  frame/timing hashes, median CPU64.343s/CUDA50.628s. Checksum-inclusive busy-host
  measurement, not a full workflow or HDR metadata qualification. No global
  GPU-decode default changed. Live lab CPU99.04% of4-core quota while host42.17%
  busy; next resource benchmark proposes8 CPUs without increasing8GiB RAM.
  Restricted wrapper cannot change Docker host limits; requires admin action.

- Admin CPU change verified: cpu.max=800000/100000 (8 CPUs). Production remains
  paused and isolated research originals remain read-only.
- MP4 case A full copy validated at28.9523% smaller; Timing case D
  at53.1323%. HDR quality case A's apparent missing checks are early exits
  after measured scene-quality rejection, not a decoder failure. Shared selection
  reporting now separates the measured failure from unexecuted scenes, retaining
  raw evidence reasons. Regression cases include a real processing-error control.
- Combined Dolby Vision/HDR10+ r42 full validation PASSED:81246 frames,86.8553%
  smaller (7.336GB), per-frame picture/timing/static HDR/HDR10+ preservation,
  RPU semantic verification and unchanged copied tracks. No source publication.
- Ordinary and combined DV still need broader quality qualification before
  automatic routing. r44 runs three10-second scenes per source at15/50/85%, using
  shared sampling, rendering and quality services with existing CQ29/CQ30.
  Aggregate sample savings are distinct from measured full-file savings. Each
  scene requires passing self-check and candidate quality. No automatic guard
  disabled. Active snapshot unchanged; subsequent DV sample decodes also use
  the shared strict diagnostic checker.

- Final local regression run630 tests,3 skipped,no failures. First run caught
  the new qualification module missing from package inventory; pyproject was
  corrected before the passing rerun. r45 Linux focused13 tests also passed.
  r44 ordinary-DV first scene passed quality (mean93.018,p5 92.526; self-check
  mean98.475,p5 98.319). Remaining scenes and combined qualification continue.
