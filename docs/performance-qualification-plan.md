# Faster processing without weaker checks

The goal is less end-to-end time and more validated storage saved per hour,
while preserving quality, metadata, timing, source protection and shared-host
safety. Research writes only separate copies; production remains unchanged.

## Next improvements

### Native reader qualification in progress

- [x] Full real AV1 CPU/GPU comparison: 227,064 frames, exact metadata and
  timing, clean EOF and unchanged source. GPU inspection took 78.67% less time.
- [x] Seven deliberately damaged AV1 controls rejected by the same executable.
- [x] One shared full-reader policy for automatic and HDR-preservation callers,
  with GPU admission, cooperative pause/cancel and no silent decode-error retry.
- [x] Complete the real static-HDR HEVC pair: 109,681 frames exact, clean EOF,
  unchanged source, 88.64% less inspection time. Dynamic-HDR coverage is separate.
- [x] Generated shared-engine reader dispatch: 1,464 frames exact; research
  profile injection only, not image-owned profile-loader certification.
- [x] Fresh same-build HEVC controls rejected all seven deliberately damaged
  inputs. Complete generated conversion, output preservation, quality (mean
  98.89 / fifth percentile 96.84), source integrity and savings (37.65%) passed
  with unchanged thresholds. This is not a real-library whole-job speed claim.
- [x] Full HDR10+ pair passed: 149,241 frames with exact dynamic/static metadata,
  timestamps and geometry/color; clean EOF and unchanged source. CPU 7,191.08
  seconds versus GPU 369.57 seconds, 94.86% less inspection time. Temporary
  manifests were removed and their absence independently checked. The one-time
  research allowance did not change production limits or quality thresholds.
- [x] Verify the image-owned reader profile and actual native dispatch in an
  isolated application container (r7). All 1,464 generated frames matched;
  CPU inspection took 6.66 seconds and GPU inspection 2.02 seconds. Complete
  output validation, quality, source integrity and savings checks passed;
  temporary files were removed before completion. The running production app
  still needs a release containing this qualified reader bundle.

Runtime evidence and live observers are retained on the development dashboard.
Reader artifacts are assembled only from completed exact comparisons and
damaged-input evidence bound to the same binary, physical GPU and driver.

- Reuse metadata reads for small generated sample clips within one job. Each
  reuse checks the complete file hash and identity; originals and full outputs
  still get fresh reads. Limit this cache to eight MiB so hashing a large sample
  does not turn a small optimization into extra storage work. A generated-fixture
  test of eight reads took 0.82 seconds without reuse and 0.12 seconds with it;
  metadata matched. That saves about 0.70 seconds in this test, not minutes per
  conversion. Full-job benefit has not been measured.
- The frame comparator now accepts streamed records through the same parser and
  checks as the file reader. Production still writes the original evidence
  format. Lossless compression was tested, not enabled: it reduced generated
  evidence storage by 98.3% on the Linux research container, but the median
  write-and-compare time rose from 0.622 to 0.654 seconds (5.1% slower). This
  excludes media decoding and cannot establish full-job performance. Evidence
  hashes and complete frame counts matched; changed geometry, timing, color,
  cadence, hidden HDR data and truncation remained rejected.
- Existing GPU admission gives short trials priority until a waiter is thirty
  seconds old. After a long active encode, that aging rule often restores FIFO
  for all waiters. A pure bounded-bypass prototype allows at most two short
  trials to pass an earlier long stage, then forces that long stage's turn.
  In the deterministic serial model, median short completion was 640 instead
  of 3040 seconds; total batch finish remained 3060 seconds in both cases. This
  improves modeled response time, not measured GPU speed or batch throughput.
  The prototype is not wired into production admission: cross-process bypass
  persistence and real shared-GPU qualification are still needed.
- Measure temporary-work storage time versus decoding time before adding SSD
  scratch storage. Moving work files helps only if storage is the bottleneck;
  source protection, output validation and verified copying must stay unchanged.

SSD scratch storage remains a qualification idea, not an enabled feature or a
promised speedup. The bundled API and UI use the same processing engine.

The latest isolated Linux run passed 73 regressions, including native OS-lock
release, cancellation and process-death checks. The first harness attempt failed
because child processes lacked its snapshot PYTHONPATH; that harness issue was
corrected before the successful run. Windows checks ran 98 tests: 87 passed and
11 Linux-only checks were skipped. Development records retain both attempts.
Generated frame-evidence files and uploaded source archives were removed;
small research records and isolated source snapshots remain for reproducibility.

## Completed work list

- [x] Inspect the initial failed/slower benchmark rather than treating it as a
  valid throughput result.
- [x] Reproduce concurrent capability initialization failures under task pressure.
- [x] Bound generated-probe and implicit FFmpeg worker pools; preserve explicit
  decoder settings and codec presets.
- [x] Separate container task exhaustion from generic GPU capability failure.
  The old research PID 1 had adopted 188 zombies under a 256-task limit.
- [x] Prepare process reaping in image entrypoints and legacy research launchers.
  An isolated Linux test reaped five generated orphans and forwarded termination;
  final image qualification remains a release-stage requirement.
- [x] Select two representative cases: a complete conversion and a correct
  no-benefit outcome, using the original queue settings.
- [x] Complete the bounded-two-worker baseline with full validation.
- [x] Complete the fixed-four-worker/stage-pool comparison with full validation.
- [x] Diagnose inherited production pause-lease interference and give research
  its own ownership-aware lease without weakening other applications' priority.
- [x] Audit all 23 initial sample durations. Three extra roughly 60-second stalls
  explain almost the entire earlier 179.39-second encoding gap; exact historical
  pause decisions were not retained, so attribution remains qualified.
- [x] Compare decoder and scoring workers across five scenes with recovered
  source decoder compatibility options. Exact evidence matched; scoring sped up,
  while short decoded-frame hashing did not meaningfully improve.
- [x] Qualify a faster complete HDR reader against both a full source and a known
  failing excerpt. Reject rollout because repeated metadata differences remain.
- [x] Test direct NVIDIA decoding. Reject it as a faster identical drop-in path:
  it was slower in this experiment and serialized timing differed.
- [x] Measure redundant packet hashing and integrate selected reads for at most
  two copied tracks. Retain full fields, error checks and independent duration
  evidence; larger track sets keep a combined pass.
- [x] Integrate adaptive two/four-worker SDR selection into the shared CLI/app
  workflow, without creating a new media-eligibility gate.
- [x] Correct unreachable free-memory requirements for the research allocation
  and stop subtracting host load twice from container CPU headroom. Preserve
  host, container, task, I/O and memory-pressure backoff.
- [x] Run 103 Linux regressions against the final frozen snapshot before media.
- [x] Complete final adaptive full-file qualification: 35.44 versus 56.55 minutes,
  same output size, source checksum, selections, plans and 76 sample records.
- [x] Verify complete source-frame evidence byte for byte and complete output
  validation. Container checksum equality is not claimed.
- [x] Verify cancellation/cleanup fixtures, Linux stage fairness and process
  control, GPU-sharing behavior, and live monitor freshness within their stated
  test scopes.
- [x] Assess retry evidence reuse. Keep existing checksummed within-run reuse;
  defer cross-run caches rather than retain large artifacts without a complete
  content/policy/recovery contract.
- [x] Audit short-job latency separately from batch throughput. The no-benefit
  case waited longer behind the full encode; report that tradeoff explicitly.
- [x] Verify code identity, preserve benchmark evidence, update the development
  dashboard and prepare next-build notes with measured limits.

## Qualification outcome

The corrected adaptive batch took 2,126.43 seconds versus 3,392.97 seconds:
**37.33% less observed elapsed time**, or **30.71%** after subtracting the recorded
baseline GPU-priority pause. Cache, run-order and other shared-host effects
remain. This is not a randomized benchmark or a universal per-file promise.

The full test copy passed automatic validation with the same **75.18%** reduction:
11,898,719,149 to 2,952,899,086 bytes. All 76 sample records and both decisions
matched baseline, excluding sample paths/time and the new worker-policy label.
Complete source-frame evidence was identical (34,853,876 bytes and matching SHA256).
The final frozen code matched 228 current Python/test files and its own manifest.

The no-benefit case still correctly kept the original, but took 1,066.53 instead
of 412.09 seconds, including 597.83 seconds of GPU admission waiting. Batch
throughput and short-job latency must not be conflated.

The first integrated adaptive run was intentionally stopped during encoding
after resource-policy defects were found. It is not a failed quality test or a
completed full-file result. Its completed no-benefit case matched baseline.
Only a waiting replacement snapshot was updated; no running code was edited.

## Release-stage follow-up, not performed by this research task

- [ ] Obtain approval to build/deploy or publish git changes.
- [ ] Build the final image and smoke-test packaging, health, entrypoints and
  PID-1 orphan/termination behavior in that image.
- [ ] Drain and, if approved, recreate legacy non-reaping research containers.
- [ ] Roll out to production and observe a broader library mix under real load.
  Other media profiles retain existing behavior until separately qualified.
- [ ] Authorize any source replacement separately. Research success alone never
  permits publication, deletion or claims of reclaimed library disk space.

No source media was replaced and production was not resumed. HDR frame-threaded
reading and direct NVIDIA decoding remain disabled for these changes. No quality,
metadata, timing, savings or source-protection gate was weakened.

See [measured results](performance-results.md) for stage timings, experiments,
test scopes and remaining limitations.

## Follow-up qualification: audio reuse and NVIDIA presets

Complete source PCM evidence can now be reused within one workflow, after
verifying the source checksum, decode options and evidence checksum. This applies
only to small sources (up to 64 MiB) and the existing decoded-audio fallback.
Every output is still independently decoded and compared. Larger sources keep
the original fresh-decode path; this is not a new eligibility restriction.

Three alternating-order runs on Linux used a generated 20-second AAC fixture.
Median comparison time fell from 0.995 to 0.825 seconds (17.1%). Source decodes
fell from four to one, output decodes stayed at four, and all comparisons passed.
This measures repeated audio comparisons, not full-file conversion throughput.

A separate RTX 5050 matrix tested ten-second 1080p SDR generated fixtures twice
in opposite preset orders. All sixteen HEVC/AV1 runs passed the existing quality,
timing, geometry, copied-track and savings checks. HEVC p5 median encode time was
1.959 seconds versus p6's 2.297 (14.7% less), with a 1.5% larger output. AV1 p5
took 1.922 seconds versus p6's 2.059 (6.6% less), with a 1.1% larger output.
Quality measurement alone took roughly 4.5 seconds per run, so these encode-only
gains must not be advertised as overall conversion gains. Production presets
remain unchanged pending representative full-file testing.

Paired SDR frame readers produced identical evidence and took 1.789 versus
2.367 seconds on this clip. This experimental path remains disabled by default;
the earlier smaller fixture showed a slowdown. Generated media was removed;
small reports and qualification evidence were retained. No library media or
production queue was changed, and no quality or savings gate was lowered.

## Complete reader follow-up

On the Linux research container, three alternating-order rounds read every frame
of a generated 30-second 1080p SDR H.264 clip. Four decoder threads took a median
1.422 seconds versus 2.671 with two (46.8% less reader time). All six complete
720-frame evidence files were byte-identical. A source/output paired run also
returned identical complete evidence. This does not qualify HDR slice decoding,
full-library throughput or permanently increasing thread counts under load.
The shared resource-admitted SDR policy remains in place; experimental overrides
exist only in the benchmark. Generated source/output copies were removed.

The duplicate-read review found existing safe reuse: source sample frame audits
are shared across candidates, output-video discard decoding is omitted after its
complete frame audit, and complete HDR source evidence collected before encoding
is retained for final validation. VMAF decoding still requires pixel data and is
not interchangeable with serialized metadata evidence. No quality read was
removed without an equivalent complete check.

Correct the shared workflow stage label during the pre-encode HDR source audit:
it is inspection, not hardware encoding. Enter encoding only when the actual
encoder command starts. This affects presentation, not validation policy.

## Shared validation scheduling

The initial fixed four-primary-worker cap was rejected: two complete generated
readers took a median 3.427 versus 2.431 seconds (41% longer). Every evidence
file matched, but correctness alone is not a performance qualification.

The revised shared allocator follows the existing sustained-headroom decision:
one stage has at most four primary reader/scorer workers; two stages may share
up to eight. OS leases release on worker death and unknown legacy workers are
treated conservatively. This budget is not a hard limit on all native helper
threads or RAM. Existing host/container pressure checks still apply.

Final validation gets priority over fresh trials, while thirty-second aging
restores FIFO ordering. Short GPU trials may yield to two queued CPU validators
for at most thirty seconds, but final validation and external GPU-sharing rules
are preserved. This limits backlog growth without changing quality or savings
requirements. No running production queue was changed for these experiments.

The revised allocator's two-reader median was 2.475 versus 2.426 seconds in
three alternating-order generated rounds (about 2% longer). Evidence remained
byte-identical. This establishes no measurable throughput gain; the scheduling
goal is bounded contention and final-file latency, which still needs a real
mixed queue comparison. Eighty final Linux regression checks passed with no
skips, including resource leases, cancellation, dead-worker recovery, legacy
compatibility, final-stage priority and partial-lock cleanup.

## Contended mixed-queue qualification

Three alternating-order comparisons used two generated trial frame audits and
one generated final frame audit, queued in that order behind an occupied slot.
One reader was allowed at a time to exercise contention without increasing
production load. This is a CPU admission/latency experiment, not a full encode,
HDR, GPU backlog or library-throughput benchmark.

Final completion fell from a median 6.487 seconds with FIFO to 2.485 seconds
with bounded final priority (61.7% less elapsed time to that final result).
The full three-audit batch took 6.487 versus 6.467 seconds: essentially unchanged.
The tradeoff is explicit: the two trials wait longer while the final audit
finishes first. Thirty-second aging remains the starvation guard.

All eighteen complete 720-frame evidence files were byte-identical. Eighty
Linux regressions passed before the experiment. Generated media was removed;
small qualification reports/evidence remain on the development dashboard.
Production was not updated, resumed or otherwise modified.
