# Animation research status — 21 September 2026

This is a checkpoint, not a final qualification or a deployment report. The
production queue is paused. Research uses read-only source and production-output
mounts; generated copies are isolated in `/work` on TrueNAS. No sources were
replaced or deleted during this research.

## Current folder coverage

Read-only inventory found 82 supported media files, with no unreadable paths or
never-processed files. Recorded history is not proof that all work is finished.

| Current production-history category | Files |
| --- | ---: |
| Converted, current file matches publication signature | 51 |
| Queued | 14 |
| Retained by measured decision | 9 |
| Retained because a workflow was blocked | 4 |
| Failed, without a later production replacement | 3 |
| Changed source with stale history | 1 |

The stale file is *HDR case A*. An older HDR10+ preservation
report exists, but it explicitly lacks quality approval and replacement
authorization. Matching size alone is not a replacement receipt. Leave the
current file untouched pending the owner's provenance confirmation.

## Historical failures

Nineteen distinct Animation sources have failed/interrupted history. Ten now
have a matching, completed production replacement:

- Library case E
- Library case F
- Efficiency case A
- Library case A
- Audio case A
- Language case B
- Library case B
- Library case C
- Library case D
- Audio case B

The other nine are accounted for below. Research success does not rewrite their
production history or authorize replacing a file.

| Source | New evidence / remaining work |
| --- | --- |
| Timing case A | Fresh complete shared workflow passed; output 59.332% smaller. |
| Timing case C | Fresh complete shared workflow passed; output 35.303% smaller. |
| Savings case A | Full candidate saved 9.033%, below the selected 10% minimum; bounded HEVC CQ refinement queued. |
| Artwork case B | Fresh complete shared workflow passed; output 76.143% smaller; quiet full-decode log clean. |
| MP4 case A | Full shared-workflow copy validated; 28.952% smaller. |
| Timing case D | Full shared-workflow copy validated; 53.132% smaller. |
| Language case A | Complete retained-output preservation/decode passed, 103,211 frames; 25.439% smaller. |
| Timing case B | Complete retained-output preservation/decode passed, 112,440 frames and 219,881 matching PCM audio frames; 26.674% smaller. This diagnostic did not repeat quality scoring. |
| Artwork case A | HEVC and AV1 sample preservation/quality passed; full shared workflow queued. |

HDR quality case A completed sample trials: measured scene quality rejected
the smaller candidates; other candidates exceeded the savings budget. Skipped
later-scene checks were misleadingly reported as missing decode/HDR evidence.
Shared reporting now distinguishes that early quality rejection from actual
processing errors, without removing the diagnostic evidence or weakening gates.
HDR case B is in full HDR validation; AV1 case A and Long encode case A follow.
Nine further full/refinement cases wait behind this batch.

The combined Dolby Vision/HDR10+ full experiment now passes all81246 frames,
RPU semantic comparison, picture geometry/color, timing, static/dynamic HDR and
copied tracks. Reduction86.855% (7.336GB); original retained. This is a successful
research copy, not automatic-route qualification. r44 adds three10-second scene
quality tests at15/50/85% for ordinary and combined DV, using the shared quality
services and unchanged floors. Automatic DV guard remains enabled. Admin's CPU
increase is verified at8 cores; no production deployment or queue resume occurred.

## Previously blocked inputs

- Legacy case A AVI: source-derived MPEG-4 color signaling and complete-GOP sample
  recovery now pass. Eligible AV1 samples estimate 41.967% reduction. Full encode
  exposed a missing final source timestamp. Original VOL/VOP clock recovery now
  passes a fresh 288-picture tail and comparison of all116855 source/output
  frames. Metadata and copied-track comparisons also passed. Final decode then
  failed on an incomplete final AC-3 audio frame. A separate complete original
  audio decode reproduced the same error; the final1040-byte packet has the same
  hash in source/output (preceding complete frames are2560 bytes). Timestamp fix
  is qualified. The user approved a separate repaired test copy: exactly the
  diagnosed final packet was removed, all video and remaining audio packets
  match, strict full decode passed, and source hashes are unchanged. User also
  reports successful playback. No source replacement is authorized.
- Legacy case B: source-derived color signaling passes; eligible HEVC
  samples estimated14.133% reduction, but the actual full copy saved7.179%, below
  the10% minimum. Keep for this candidate/settings; no full validation or replacement.
  Bounded HEVC CQ refinement is queued, retaining the same quality/savings floors.
- Legacy case C: revised size-directed search completed. AV1 CQ28 saved
  20.834% in samples but fifth-percentile VMAF was86.380 (90 required); CQ27
  also missed quality, while CQ26 saved only8.384% (10% required). Reference
  self-check passed. Retain under current settings; missing color no longer
  prevents evaluation.
- 4:4:4 case A: samples pass at 41.860% reduction. The previous
  decode problem was missing original x264-build SEI context in excerpts,
  not a resolution or GPU limitation. All four 4:4:4 series sources now passed
  three-scene tests, with estimated40.415–47.653% savings across the set.
- Dolby Vision profile8.1: DV series B full retained-copy verification passed,
  60773 frames,10.208% smaller, exact RPU semantics and static HDR, copied tracks,
  chapters and timing preserved; full video/audio decode passed. This active
  snapshot predates the additional per-frame picture-signature guard, which is
  covered by current regression tests, not claimed retroactively for this copy.
  Combined Dolby Vision/HDR10+ three-scene tests passed selected settings; its
  first full attempt hit the old3600s frame-audit timeout near93%. r42 retries
  with duration-aware limits and current shared verification. The
  production skip guard remains enabled. DV case C remains
  an actual unqualified Dolby Vision input, not a claimed success.

## Fast keep decisions

Efficiency case B is a regression example for retaining a file without repeatedly doing
expensive work. Its last full AV1 output saved only **4.919%**, below the selected
10% threshold. This proves that candidate missed the target, not that no encoder
could ever improve it. Efficiency case C is a sample-based no-savings example.
Efficiency case A demonstrates why an old no-savings result must not be permanent:
it was subsequently converted successfully under different evaluation settings.

Cache decisions against source identity, relevant settings and evaluation
policy. Reassess changed policy once; preserve successful replacement and
explicit-keep decisions. Do not declare files optimal from codec names alone.

## Single-host performance evidence

- History lookup synthetic test: 10,000 records / 1,000 lookups took 1.197s
  before indexing versus 0.00470s including index construction. This is a UI/
  scheduling improvement, not encoding throughput.
- Generated SD complete-validation benchmark: median 2.511s before versus
  1.800s current, 28.310% less validation time. Not a whole-library speed claim.
- Generated 720p HEVC pixel/timing decode check: CPU 1.699s, CUDA plus download
  1.943s. GPU validation was slower here and is not enabled globally.
- Research container has four CPU cores of quota and eight GiB of RAM, on a
  shared 12-vCPU host with an RTX 5050. CPU-heavy quality/frame checks can remain
  the bottleneck while the encoder is partly idle. More GPU utilization alone
  is not evidence of faster validated throughput.
- Dynamic admission now considers both host load and container CPU/RAM limits.
  Keep jobs bounded; benchmark a larger CPU quota before increasing concurrency.
  No multi-machine/distributed processing is proposed.
- A 24-frame HDR comparison confirmed decoder-only thread bounding preserves
  every measured metric value exactly. Median time14.197s versus13.486s (~5%
  lower) and median peak RSS3.463GB versus2.435GB (~30% lower). An earlier attempt
  to also bound filter threads changed scores and was rejected; filter behavior
  remains unchanged. These are microbenchmark results, not overall job speedups.
- Real 4K HEVC240-frame CPU/CUDA checksum comparison (ABBA) passed with exact
  decoded pixels/timing. Median CPU64.343s vs CUDA50.628s (~21.3% less elapsed).
  This includes checksum cost and shared-host contention, not pure decode time;
  it does not qualify GPU HDR/DV metadata inspection or enable GPU validation
  globally. r43 retains commands' outputs and the comparison report.
- Latest live sample: research CPU allocation99.04% used (4-core quota), host
  CPU42.17%, lab memory2.70/8GiB used. An8-core research-only benchmark needs an
  admin Docker action; restricted research access cannot change host limits.

Latest complete local regression run: **625 tests run, 3 skipped, no failures**.
Decoder-only adjustment and narrow MPEG-4 source-clock recovery are included.
All three Windows-skipped Linux locking/restart tests passed in the isolated
TrueNAS container, together with eleven timing-recovery tests (14 total).
Remote full-file
research remains in progress; no release, deployment or Git writes were made.

Ordinary DV final mux exposed a process-exit/memory-observation race, reproduced
in 98/100 short Linux trials. The shared guard now rechecks within 100ms and
still rejects live missing telemetry, memory overage, and nonzero exits. Recovery
reused the completed encode: fresh ordered mux passed in 23s, full RPU semantics
matched, and complete frame/decode verification passed at10.208% reduction.
The combined DV/HDR10+ retry is active and remains unqualified as a full file.

New phase transitions clear stale percentage/ETA data. Future full HDR frame
audits use a bounded, duration-aware timeout. Two additional unit tests cover
source-derived per-frame geometry/color preservation in the experimental DV
verifier; older compact evidence is refreshed automatically for this check.
Active research snapshots have not been modified underneath running processes.

Generated corrupt/truncated fixtures exposed FFmpeg diagnostics with exit zero
even when `-xerror` is used. The shared stage runner now offers strict decoding
that rejects non-progress diagnostic lines immediately, before log truncation.
Automatic full output validation, AAC PCM validation and experimental DV final
decodes opt in; normal encode/probe logging is unchanged. All 38 focused tests
also passed in TrueNAS. Existing completed research decode logs were audited:
no hidden diagnostics found in r9/r27. Waiting r26 received the fix; active jobs
did not. Shared validation now reuses its current successful full-frame video
decode and finishes with strict decoding of every audio track. Missing complete
evidence falls back to full video/audio decoding. Generated corruption/truncation
and copied-bad-audio tests pass; r40 Linux suite68 tests passed. Waiting r26 has
this change; active snapshots and the production app do not. Ordinary DV audio
alone passed in30.826s; the old full video/audio finishing stage completed in1211s.
Both were run against the same retained output on a shared busy host. Avoiding
that second video decode can eliminate roughly20 minutes here; this is not a
controlled whole-workflow speedup claim and does not eliminate the first audit.

Retained full-decode logs for all51 production replacements were audited.49 were
quiet; Audio case A and Audio case B had DTS-HD
diagnostics despite exit zero. Saved reference/output audio packet evidence is
identical in every field (164079 and155393 packets respectively). Fresh complete
audio-only decodes of both current files passed without diagnostics in64.494s
and62.579s; SHA256 hashes exactly match their published outputs. The old warnings
were not reproduced in these checks. No repair or source mutation was performed;
the historical logs are retained, not rewritten as clean.
