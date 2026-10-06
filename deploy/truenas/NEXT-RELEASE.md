# Next release deployment checklist

## Compact sci-fi console presentation

- The latest preview refines this into a retro operations terminal: olive-black
  panels, green progress readouts and amber headings, with a matching light theme.
  Queue rows are tighter; measured progress does not pulse or simulate activity.
  An unknown percentage retains a reduced-motion-aware working indicator.
- This presentation is integrated into the shared app UI, not just the preview.
  Wide screens show filename/size, activity/timing, progress and expandable
  details side by side. Narrow screens stack these fields without clipping text.
  Help and the footer share a compact strip; secondary queue guidance stays
  inside the settings disclosure. No image build or deployment has been performed.
- The workspace uses instrument-style typography, angular panels and segmented
  progress bars. Bars are limited to 360 pixels on desktop and 280 on mobile,
  rather than stretching across the job card.
- Plain-language controls, light/dark themes, keyboard focus, reduced-motion
  behavior and live progress semantics remain intact. This is presentation only;
  processing, quality checks and replacement rules have not changed.
- The local design preview uses sample data and cannot operate on the library.

## Copied audio timestamp failures under qualification

- The shared Matroska mux builder now preserves the source timestamp scale and
  uses the passthrough packetizer for Matroska TrueHD inputs. A complete
  real-source audio-only qualification matched 8,481,771 TrueHD packets and
  220,879 companion audio packets exactly: payload, order, PTS, DTS and duration.
  This is transport evidence, not full converted-video or publication approval.
- The older DTS case requires a direct packet relay: ordinary packetizers and
  external timecode attempts changed presentation timestamps and were rejected.
  An isolated direct relay, followed by Matroska assembly with original
  subtitles and metadata, matched all 534,980 audio packets exactly. Subtitle
  and metadata parity now pass, including original audio selection flags and
  copied subtitles/chapters. The relay is integrated into shared recovery and
  passed against the already-pinned PyAV 18.1.0 dependency. Generated end-to-end
  DTS and TrueHD conversions passed full validation and VMAF checks on Linux.
  Both real-source GPU conversions now passed complete automated validation:
  the HDR/Dolby Vision + TrueHD case was 39.20% smaller and the SDR + DTS case
  was 51.16% smaller. Both source file identities remained unchanged. Outputs
  are separate research copies, not published replacements or reclaimed space.
  Final image qualification remains pending. The running app has not changed.
- Copied-track failures now identify the track, packet and changed field.
  No timing tolerance, decoded-audio, quality or replacement check was relaxed.

## Resolution and bitrate presets (development only)

- A shared selector adds original resolution, 1080p / 8 Mbps video, 720p /
  4 Mbps video and 480p / 1.5 Mbps video. Target geometry preserves display
  aspect without cropping or upscaling. Audio and subtitles remain copies.
- Target-resolution quality checks use explicitly resized references with
  mean/p5 floors of 95/90, 93/90 and 90/90 respectively. These are initial
  project policies, not Plex certification or percentages of retained quality.
  Original-resolution checks are unchanged; user-supplied stricter floors win.
- Full video packet bitrate is measured before approval; VBV configuration
  alone is not accepted as proof. Preset/HDR choices are persisted in queue
  requests and considered when reusing history. Replacement confirmation warns
  that lower resolution permanently discards detail.
- Generated progressive SDR conversions passed geometry, timing, metadata,
  packet bitrate and VMAF checks for all three targets. RTX 5050 generated
  H.264, HEVC and AV1 outputs passed all three targets as well (nine GPU cases).
  Real-media presets, resized
  interlaced output and HDR transformations need additional qualification.
- HDR treatment is a per-request user choice: preserve HDR or convert to SDR.
  Requested HDR resizing / tone mapping currently retains the source with an
  explicit explanation; it is not yet an enabled, qualified conversion route.
  No app deployment or source replacement has been performed.

- Controls polling serves a cached snapshot immediately while one background
  reader refreshes history. Historical log and receipt reads no longer hold
  the queue mutex. Delayed snapshots retain their timestamps and are visibly
  stale; queue actions are disabled until current status returns.
- GPU admission primes host and container CPU counters before its first GPU
  reading. The previous fresh-stage sampler had no CPU interval, incorrectly
  reporting unavailable telemetry despite working GPU measurements. A read-only
  TrueNAS check reproduced the missing first CPU value and verified all required
  fields in the second sample. Missing measurements still retain serial admission.
- Targeted verification: 67 Linux reader/admission regressions passed; local
  control, resource and polling tests passed with platform-specific skips.
  These changes are pending packaging; installed v52 remains unchanged.

- Optional native GPU frame inspection now has one shared command policy for
  automatic and HDR-preservation callers, cooperative pause/cancellation and GPU
  resource admission. It requires completed exact frame-reader and damaged-input
  evidence bound to the shipped binary and qualified runtime. Until that evidence
  is complete and bundled, CPU inspection remains the default. No quality gate is
  weakened. The release builder accepts `--gpu-reader-bundle` and includes its
  pinned source archives, patch and license notices. No bundle is published yet.
  A full real AV1 comparison has now passed: 227,064 frames with exact metadata
  and timing, 78.67% less reader time, and seven rejected damaged controls. Its
  Static-HDR HEVC also passed: 109,681 frames matched exactly, with 88.64%
  less inspection time and seven rejected damaged controls. The combined
  artifact is prepared outside the repo. Generated shared-engine conversion
  passed the existing quality, preservation, source-integrity and savings
  checks; it is not a real-library total-speed result. HDR10+ whole-file parity
  also passed: 149,241 frames exact, clean EOF, unchanged source and 94.86%
  less inspection time (1h59m51s to 6m10s). All three scopes are assembled into
  one binary/runtime-bound artifact. The isolated image-owned loader test is
  complete: r7 accepted the image-owned receipt and dispatched the native
  reader for source and final-output inspection. All 1,464 generated frames
  matched; full validation and unchanged quality/savings gates passed.
  Temporary files were removed before completion. Include the assembled bundle
  in the next release. Dolby Vision, HLG and other-device coverage remain separate.

- The API remains bundled on the dashboard port. `GET /api` lists available
  endpoints and versions without starting work. Host checks and existing write
  protections are unchanged. Usage and trusted-network limits are documented
  in `docs/app-api.md`, which is included in the release context.
- Generated sample metadata can be reused within a job for files up to eight
  MiB, after a full content hash and identity check. Sources and output metadata
  validation are not cached. Small-fixture timings are encouraging but do not
  establish a full-conversion speedup.

- Adaptive GPU-stage admission starts serially, measures comparable stage rates,
  and tests at most two under sustained headroom. It retains two only with a
  measured 10% aggregate-rate gain, backs off under pressure/sharing requests,
  and preserves CPU/publication pools and all quality checks. Quiet-mode new
  workers stay serial. Dashboard resources include the stage limit and reason.
  Policy/OS-lock qualification is separate from real-GPU throughput evidence;
  the running app is unchanged. See `docs/adaptive-gpu-admission.md`.

Measured performance evidence and its limits are summarized in
[`docs/performance-results.md`](../../docs/performance-results.md).

- Copied-track validation avoids hashing re-encoded video when at most two
  copied tracks are present. Every copied packet hash and timestamp is retained;
  larger sets use the combined reader. Separate complete duration-header and
  decoding checks are unchanged. Repeated full-source reads matched exactly
  and took about 18 versus 62 seconds on the measured layout. Final integrated
  qualification passed; isolated reader timing is not an end-to-end speedup claim.

- Development observers can display measured progress from older workers that
  lack stage timestamps. They require an observed percentage change, expire it
  after 60 seconds, reset on phase/worker changes, and never treat heartbeats or
  100% as job completion. Zombie remote PIDs are stale, not live. Seventeen Linux
  monitor regressions passed; only read-only local observers were restarted.

- The standalone package manifest now includes the shared GPU-activity,
  cooperative-pause and owned-worker modules. A 75-test Linux integration run
  passed with the complete manifest; this fixes an installation omission, not
  a new processing or quality policy.

- Adaptive bounded SDR worker budgets are integrated into the shared workflow,
  not a separate TrueNAS path. Qualified progressive eight-bit H.264/HEVC SDR
  stages can use four workers when CPU/allocation, memory, I/O and task headroom
  permit; pressure or missing telemetry retains two. Explicit decoder options,
  filter/output pools, quality models and gates are unchanged. HDR/interlaced
  and other profiles keep their existing paths. The corrected adaptive research
  arm passed full validation in 35.44 versus 56.55 minutes (37.33% less observed
  wall time; 30.71% after the recorded baseline GPU pause), with identical savings,
  selections, plans and 76 sample records. Complete source evidence also matched.
  Its no-benefit case took 1066.53 versus 412.09 seconds, including 597.83 seconds
  of GPU admission waiting. Shared-host load, cache/order effects and short-job
  latency limit this result; do not claim a universal or deployed speedup.
  See `docs/performance-qualification-plan.md`.
  Follow-up qualification also corrects an unreachable eight-GiB-free requirement
  in an eight-GiB allocation: SDR requires six GiB remaining and a direct host
  reserve or the existing bounded ARC proof. CPU/task/pressure backoff remains.
  Twenty-four focused tests passed. The corrected frozen snapshot passed 103
  Linux tests before the now-completed full-file follow-up. Frozen code matched
  228 current Python/test files. Faster HDR and direct NVIDIA decoder shortcuts
  were rejected after testing; existing paths and gates remain unchanged.

- Explicit reader progress now timestamps stage evidence. Previously the reader
  could report a fresh percentage but the remote dashboard discarded it as
  stale. Heartbeats do not refresh that evidence timestamp; unknown/waiting
  stages still clear their percentage. No processing policy changes.

- Built-in container process reaping and task-count telemetry. Research exposed
  188 unreaped children under a non-reaping PID 1, exhausting a 256-task limit.
  New image entrypoints use tini and legacy detached research launchers use
  Docker init. Static packaging tests passed; an isolated Linux subreaper test
  reaped five generated orphans and forwarded termination successfully. Final
  image PID-1 lifecycle still requires qualification. Existing containers are
  not changed by this fix.

- Bound previously implicit FFmpeg filter and input decoder pools, plus NVIDIA
  output thread counts. Preserve explicit thread options and codec/quality
  parameters. This addresses reproduced container thread exhaustion during
  capability probing and full encoding. Both the fixed-four candidate and final
  adaptive workflow passed complete SDR conversion and validation.

- Native-stage GPU-sharing pauses have a separate wall-time counter so time
  deliberately yielded to another application is not mistaken for processing
  speed. Older timing records are not retroactively reclassified.

- Generated encoder capability checks bound FFmpeg threads, avoiding reproduced
  concurrent thread-exhaustion failures in a task-limited research container.
  The GPU scheduler recognizes stream-qualified codec options such as `-c:v:0`.
- Full-file DV evidence collection uses shared CPU-reader admission and measured
  slice-thread budgeting; HDR10+ JSON is compact without dropping frame fields.
  Frame-threaded/GPU metadata readers remain research-only.

- Current-activity labels distinguish CPU HDR/DV inspection, CPU HDR frame
  validation, explicitly reported NVIDIA full encoding, and resource waiting.
  Unknown encoder phases do not imply GPU usage. Display-only change; the live
  processing path and validation requirements are unchanged.

- Stage pools: CPU validation and GPU work can overlap; NVIDIA encoding and
  GPU quality filters share bounded GPU admission. Final publication is serial.
  GPU-sharing leases block new GPU stages; existing suspension, whole-job limits,
  free-space checks and publication validation remain intact. Drain old workers
  before deployment. The measured two-file qualification passed; broader
  production-load observation remains a rollout requirement.

- Explicit validation admission versus processing timers, restored check labels
  after resource waits, and lightweight live timing refresh. The workspace shows
  observed waiting separately; legacy records are labeled rather than assumed to
  have zero wait. These counters are wall time, not CPU time or proof of speedup.

- Audio preflight uses sample-count timestamps only for the discard decoder
  sink, avoiding null-muxer duplicate-DTS false failures. Strict decoding and
  independent source/output timing checks remain mandatory. Generated duplicate
  timestamps and truncated-audio regression fixtures cover both paths; the
  affected production source still needs a retry after deployment.
- Failed dashboard results retain execution errors when outcome errors are blank;
  missing evidence is explicitly reported as unavailable, never as a validation
  pass. This does not invent causes for historical failures.

- Fair heavy-validation admission with abandoned-ticket recovery and a second
  slot only after sustained measured headroom. Reduced capacity drains active
  checks without interrupting them. See `docs/validation-scheduling.md`. Pending
  shared-host performance qualification; no quality checks changed.

- Dashboard polling: immediate cached responses, one background discovery at a
  time, lightweight active-job heartbeat refreshes between historical scans,
  30-second browser request tolerance and single-flight polls. Rendering errors
  are not labeled as network loss. See `docs/dashboard-polling.md`. Not deployed
  in v45; processing and queue settings are unchanged.

- Reliability changes: broader missing-header DV inspection, five-section
  long-video sampling, source-identity-aware retry history, shared heavy-reader
  admission, generated-output manifests, terminal-job cleanup reconciliation,
  durable publication finalization, and clearer development outcomes. See
  `docs/conversion-reliability.md`. Audio tracks are not dropped automatically.

- Automatic HEVC quality failures can use one existing adaptive slot for a
  source-derived peak-rate retry, after a generated-frame capability test.
  Difficult-scene ordering now carries across candidates; result labels separate
  size, quality and processing failures. No thresholds or baseline settings are
  relaxed. Evaluation policy advances for newly submitted requests. See
  `docs/measured-rate-retry.md`; not deployed or a guarantee of new savings.

- Fresh automatic NVIDIA DV Profile 5/7 results now qualify for the common
  replacement publisher only after full identity, frame/track, layer, native
  quality and compatible-fallback checks pass. Explicit experimental results
  stay copy-only; old copies are not silently promoted. Generated-only
  publication transactions passed. See `docs/dv-replacement-enablement.md`.
- The app result reader now accepts validated MP4/MOV preservation outputs using
  the same explicit-container contract as the publisher, not an MKV-only rule.
  Copy-only research paths retain their output with a qualification explanation
  instead of attempting unauthorized publication and reporting a generic error.
  This does not enable replacement for those unqualified workflows.
- New requests default to size-aware savings: smaller of 25% or 1 GB, minimum
  100 MB (decimal). Fixed percentage remains selectable. Preview shows each
  target; trials use its effective percentage, full output and publication check
  the actual byte saving. Existing jobs retain their saved fixed settings.
- Cover artwork between the main video and copied tracks no longer causes an
  automatic rejection. Remapping preserves metadata and compares copied packets
  against their corresponding output tracks. Cover-first, unlabelled artwork and
  multiple moving-video handling now have generated-fixture validation. Known
  interlaced SDR reaches runtime capability checks; outputs must preserve fields.
  HEVC/AV1 field-mode initialization failed on the tested NVIDIA card, while a
  generated H.264 field-preservation probe passed. No automatic deinterlacing or
  unrequested codec fallback is enabled.
- See `docs/source-driven-admission.md` for current test evidence and limits;
  generated fixture results are not certification of every container or GPU.

- Automatically route supported single-layer Dolby Vision Profile 8.1 sources
  through the qualified NVIDIA HEVC preservation adapter, including combined
  HDR10+. Include CQ24 in default trials. Authorize ordinary verified replacement
  only after all per-file quality, savings and metadata checks pass. Explicit
  experimental runs and previously unqualified outputs remain copy-only.
- The NVIDIA DV sample/full path preserves additional video tracks and restores
  nonzero and variable presentation timestamps from decoded evidence. Nominal
  rate labels may differ only after complete decoded timing/count validation.
  Size-aware byte targets are passed unchanged through the inner full-file
  service and rechecked by the publisher; no percentage rounding round trip.
- Evaluation policy advances so outdated skip decisions can be reconsidered on
  a new folder request; do not silently requeue historical work or publish old
  research outputs. Fresh shared Profile 5/7 results now have the publication
  qualification described above; old research copies remain unapproved. This
  does not qualify every GPU.

- FEL research now passes native reconstruction and compatible-fallback checks
  with the current image's FFmpeg 8.0.1 and NVIDIA encoding. The Docker context
  requires `--fel-runtime-archives` with the checksum-pinned archives and license
  accepted by `tools/install_fel_runtime.py`. The runtime loads only in renderer
  children and requires Linux x86-64, Python 3.12 and AVX2. The updated image
  passed isolated build and non-root FEL, Profile 5 and MEL runtime qualification.
  Review dependency source/notice delivery before distributing binaries.
- Native DV GPU rendering needs NVIDIA graphics libraries as well as video and
  compute libraries. The image requests `compute,video,utility,graphics`; check
  that an existing app environment override does not remove `graphics`.
  This does not change GPU assignment or host drivers.

- Correct the existing custom app's portal link to use HTTP and the published
  host port (8767 in the current installation), path `/`, rather than container
  port 8765. Preserve the existing port mapping. Verify the TrueNAS portal button
  opens the dashboard after deployment. This is a TrueNAS app setting, not a
  Docker image change; an image update alone does not repair an existing link.
# GPU monitor installation and reboot recovery

- Package a populated, self-contained GPU monitor installer with the app context.
- Register the host's TrueNAS Post Init task automatically and reuse it on reinstall.
- Store telemetry in `/var/lib/muxmender-gpu-monitor`, which survives normal reboots.
- Upgrade only validated root-owned monitor files; keep the existing app permissions.
- Include migration instructions from the old volatile `/run` mount and optional setup.

# Additional performance work (qualification pending)

- Disable Resume unless the queue is paused and has waiting jobs. Empty,
  terminal-only and already-running queues cannot be resumed through the API;
  rejected requests leave pause state and failure counters unchanged.

- Coordinate primary validation workers through shared OS leases: four with a
  single stage, up to eight only after sustained headroom permits two stages.
  This is not a hard CPU/RAM cap; native helper threads remain separately bounded.
- Final CPU validation may pass fresh trial checks; waiting thirty seconds
  restores FIFO priority. Unknown/legacy tickets retain FIFO treatment.
- New short GPU trials yield for at most thirty seconds when two or more CPU
  validators are queued. External GPU sharing remains authoritative. Final
  validation is not held back by this trial-backlog policy.
- Reject the initial fixed-four-worker policy: its generated two-reader batch
  was 41% slower. Use measured headroom rather than permanently reducing workers.
- Contended generated queue tests: final frame audit completed 61.7% sooner
  under bounded priority, while full batch time was essentially unchanged.
  All eighteen complete frame reports matched. This is a final-latency result,
  not a full-conversion speedup or GPU/HDR qualification.

- New processing requests automatically start a queue stopped by cancellation.
  Cancelled jobs remain cancelled. Manual, error and restart-recovery pauses
  still require Resume. Keep-only or history-skipped requests do not restart
  processing. Resource and GPU-sharing limits still govern worker admission.

- Reuse current-run complete strict PCM validation for audio tracks that already
  passed presentation and packet checks; decode remaining tracks independently.
- Stop quality-limited retries after a preserved, decoded scene fails measured
  quality, before encoding their remaining clips. Approval still requires every scene.
- Give short GPU trials limited priority while aging queued work after 30 seconds.
- Keep private authenticated source-audio proofs for retries, bound to a complete
  source checksum, decoder binary/version/options and validation code. No output
  approval or media artifact is cached. Limit records to 2,048 and reuse to 30 days.
- Prepare paired complete SDR frame readers under the existing admission policy.
  This experimental CLI path remains off until equivalence and speed are measured.
- Include an isolated NVIDIA p4/p5/p6/p7 benchmark using the shared quality and
  preservation checks, automatic working-file cleanup, and dashboard tracking.
- Keep production encoder presets and all quality, metadata and savings floors.

## Bounded NVIDIA qualification result

The RTX 5050 research image passed 145 regression tests, including generated
media checks, followed by 65 post-fix tests. Sixteen five-second SDR runs across
HEVC/AV1 p4/p5/p6/p7 passed preservation, full-frame and quality checks. Median
encoding times were approximately 0.69–0.80 seconds: startup dominated and
there was no meaningful preset speed improvement. Production presets are unchanged.

Paired readers returned byte-identical frame evidence but took 1.55 seconds
versus 0.37 seconds sequentially on this fixture. They remain disabled. This
does not establish full-library performance or HDR qualification. Both attempts
cleaned their generated media and frame/quality work files, retaining reports.

## Additional qualification, 2026-10-02

- Include bounded within-workflow source PCM evidence reuse for the existing
  audio fallback. Complete source/evidence hashes must match; outputs always
  receive fresh strict decoding. Larger sources retain the original path.
- Alternating-order Linux audio tests passed with 17.1% less comparison time,
  not a claim about total conversion throughput.
- Ten-second RTX 5050 SDR preset tests passed all sixteen cases. HEVC p5 encoded
  14.7% faster than p6; AV1 p5 6.6% faster. Outputs were slightly larger.
  Keep production presets unchanged until representative full-file qualification.
- Paired frame readers and bounded short-job scheduling remain experiments, not
  enabled production policies. No quality, preservation or savings checks change.

- Label the full HDR source-frame precheck as inspection; show encoding only
  after that check finishes. Do not mistake an idle encoder during this CPU
  audit for a software encode.
- Additional generated 30-second SDR reader qualification: four threads took
  46.8% less reader time than two across three balanced rounds, with identical
  complete frame evidence. This supports the existing headroom-controlled SDR
  policy, not unrestricted concurrency or HDR changes.

## Copied audio mux recovery (pending deployment)

- The media workspace uses the status dashboard's slate/white/green palette,
  with a matching dark theme. Current work shows a compact animated bar for
  the current check, not an invented whole-video percentage. Steps and detailed
  timings are collapsed by default. Unknown progress is striped; stale or frozen
  displays stop animation and omit a current percentage. Reduced-motion settings
  disable animation. Display changes do not alter conversion or quality policy.

- Chapter preservation now distinguishes stored chapter ends from endpoints
  inferred by a reader. A reported end mismatch is accepted only for chapters
  without an explicit end, with unchanged starts/tags and an exactly matching
  native Matroska chapter tree (including IDs, language, hierarchy and flags).
  Missing extraction evidence or real chapter edits still fail validation.
- The reported full-source case reproduced a one-millisecond inferred final
  chapter end difference with all 16 stored chapters identical. The shared fix
  passed a read-only-source remux test and rejected a deliberately edited
  chapter. Full conversion qualification must still be rerun; no deployment
  or replacement is approved by this targeted chapter test.

- A full SDR Matroska encode that fails specifically on a copied audio DTS
  regression can retry as a video-only encode, then combine that video with
  the original tracks using the shared MKVToolNix preservation mux builder.
- Do not rewrite timestamps, resample audio, apply sync offsets, or waive
  packet/PCM, metadata, frame timing, quality or savings checks. A recovery
  output is only a candidate awaiting the ordinary full validation.
- Cancellation, unrelated decoder/encoder failures, HDR preservation routes,
  sample encodes and non-Matroska sources do not take this retry route.
- Only an unchanged registered failed generated output can be removed. Keep
  the normal terminal cleanup and retained diagnostics for the recovery files.
- Linux qualification: 77 tests passed, including a generated two-second DTS
  source, video re-encoding, original-track muxing and full preservation checks.
  This is not full-file qualification of the reported library failure. The
  production queue and installed v51 image were not modified.

## HDR GPU inspection research (not enabled)

- A read-only 240-frame excerpt of the timed-out 4K source took 14.40 seconds
  with the four-thread slice CPU reader and 5.96 seconds with CUDA decode,
  download and equivalent planar 10-bit output: 58.6% less time in this single
  comparison, not a full-file or whole-workflow speedup.
- Pixel checksums, clocks, geometry/color and printed HDR10/HDR10+ traces
  matched except for chroma location: CUDA reported it as unspecified.
  Do not normalize this mismatch away in production validation.
- Three-second generated 4K tests were startup/download dominated and slower
  on CUDA. Qualification must cover realistic longer workloads, contention,
  exact JSON/side-data parity (printed floating-point traces are insufficient),
  malformed/truncated inputs and full EOF draining before integration.
- Research is tracked on the development dashboard; no production image,
  source file, queue setting or quality threshold was changed.
