# Roadmap

Our goal is simple: make an existing video library smaller without losing what
makes it worth keeping. A smaller file only counts when it passes the selected
quality and preservation checks.

This roadmap describes the code in main, not what is installed on your server.
See the [status report](STATUS.md) for recorded results. Priorities are not release promises.

## Already in the code

- [x] Shared processing services for the app and standalone tools.
- [x] File/folder selection, recursive scanning and remembered processing decisions.
- [x] HEVC/AV1 trials, with reasons for keeping or converting each file.
- [x] Separate analysis, sample-test, safe-copy and approved replacement actions.
- [x] Processing steps, resource information and recorded space savings.
- [x] File creation-age filtering: all files, hours, days or weeks.
- [x] Generated-file cleanup after verified replacement, with job history retained.
- [x] GPU capability checks and job admission based on shared-host resources.
- [x] Regression tests for timing, color, copied tracks and interrupted work.

These features still need deployment and real-file checks where noted below.
A unit-test pass does not qualify every video or GPU.

## Next: finish the current library checks

- [ ] Finish remaining full-file tests and size/quality refinements. Give each
  result a clear outcome: converted, deliberately kept, failed, or waiting.
- [ ] Reconcile historical failures with later successes without erasing history.
- [ ] Investigate the file whose current contents no longer match its old history.
- [ ] Repeat the recursive animation-folder audit: every current file needs an
  explanation, with no silently omitted files.
- [ ] Find ordinary Dolby Vision settings that meet both quality and size targets.
- [ ] Integrate and qualify the successful combined Dolby Vision/HDR10+ experiment
  in the shared automatic workflow. Keep automatic routing disabled until then.
- [ ] Prepare an agreed deployment package and check recovery before the next
  long production run.

## Next: spend less time on each file

- [ ] Queued September 22: benchmark faster NVENC presets on the TrueNAS RTX
  5050 against the current preset, using separate test outputs after production
  GPU capacity is available. Compare HEVC and AV1 where supported, using the
  same source windows and repeated measurements. Record encoding FPS/time,
  quality scores, output size, resource use and end-to-end validation time.
  Keep the selected quality and preservation requirements unchanged. Check
  one versus two concurrent jobs for total throughput, not just per-job time.
  Recommend settings from measured results before considering a GPU upgrade;
  do not change production settings or replace source files during the benchmark.
- [ ] Improve early no-savings decisions using measured samples, not filenames or
  codec names alone.
- [ ] Reuse results only while the source, settings and evaluation rules match.
  Allow reassessment when relevant settings change.
- [ ] Compare the eight-CPU research allocation with the earlier four-CPU setup,
  then recommend CPU, RAM and concurrency settings.
- [ ] Broaden CPU/GPU validation benchmarks before enabling GPU validation
  automatically. GPU use only helps if it improves checked throughput.
- [ ] Reuse completed checks safely without hiding corruption or dropping checks.
- [ ] Measure whole-job time and storage use, not just individual-stage speedups.

Performance work stays on one host. Multi-machine processing is out of scope.

## Broaden compatibility

- [ ] Expand NVIDIA generation coverage, including older cards and multiple GPUs
  on one host. Test encoding and decoding separately.
- [ ] Re-test AMD against the current shared engine and broaden Intel coverage.
  One card's limitation must not block a working route on another.
- [ ] Finish full-file tests for selected 10-bit 4:4:4 inputs; short tests passed.
- [ ] Broaden legacy AVI, mixed-container, audio, subtitle, aspect-ratio and timing tests.
- [ ] Research other Dolby Vision profiles and HLG separately. Never quietly
  remove HDR information or enhancement layers.
- [ ] Exercise missing dependencies, cancellation, restarts, low disk space and
  hardware failures across platforms. Ask before installing software.

## Make everyday use easier

- [ ] Keep lifetime savings, active steps and resource information easy to find
  on narrow screens and long result lists.
- [ ] Check dark mode, keyboard access, focus, screen-reader feedback and contrast
  against Section 508 expectations. Automated tests alone are not certification.
- [ ] Make kept, failed, waiting and completed results easy to distinguish,
  with a useful reason and next action.
- [ ] Keep setup and advanced filters out of the way once a job starts.

## Later, if useful

- [ ] Optional lookup of missing descriptions, dates, ratings and artwork.
  Keep it off by default, preserve user edits and ask about ambiguous matches.
- [ ] Broaden playback tests and distinguish direct playback from server
  transcoding, especially when subtitles are enabled.

## Rules that do not change

Keep the original resolution unless the user requests otherwise. Safe-copy mode
keeps originals. Replacement is an explicit choice and permanently removes the
original only after successful checks. Never silently repair damaged source
audio, weaken a quality target, install a driver, or enable an unqualified HDR
route. Use neutral example names throughout the repository.
