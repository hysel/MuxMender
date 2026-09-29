# Dolby Vision FEL research copies

Historical research record. For current automatic routing and replacement
eligibility, see [supported use cases](SUPPORTED-USE-CASES.md) and
[verified DV replacement](dv-replacement-enablement.md). Earlier copy-only and
not-deployed statements below describe their checkpoint, not current v41 policy.
Explicit experimental outputs still remain copy-only.

Phase 1 targets NVIDIA. AMD and Intel qualification is deferred.

We are working toward smaller Profile 7 FEL files without silently discarding
the enhancement picture information. FEL is not yet an automatic replacement
path. A Dolby Vision badge or a good HDR10 fallback score does not establish
that the reconstructed FEL picture is correct.

## What you can run now

The explicit research command reuses the shared layer-preservation encoder.
It re-encodes the base layer with NVIDIA HEVC and retains the enhancement video,
ordered RPU metadata and copied tracks. Timing, geometry, metadata and track
checks still apply. By default it measures the HDR10 fallback as a diagnostic,
not as proof of native FEL quality. The result is labelled
`unqualified-fel-research-copy` and remains outside automatic replacement.

Start with a dry run:

```sh
python3 tools/dv_fel_research.py /research/source.mkv --output-dir /research/fel-preview
```

To make a separate research copy:

```sh
python3 tools/dv_fel_research.py /research/source.mkv --output-dir /research/fel-preview --execute --acknowledge-unvalidated-fel
```

Use a fresh output directory. The command never overwrites or replaces the
source. `--cq` controls the experimental NVIDIA setting, not a quality guarantee.
`--ffmpeg` and `--ffprobe` select reader/validation tools; `--encoder-ffmpeg` can
select a separate driver-compatible encoder build. These builds must actually
support the input and hardware. The job writes progress and diagnostic reports.

An optional `--fel-render-plugin /runtime/libfelbaker.so` enables the shared
streaming native-picture comparison when the separate qualified VapourSynth
runtime is available. `--fel-render-python` selects its Python executable;
the runtime's library and Python search paths must be configured in the caller's
environment for a manually configured runtime. A runtime staged by the helper
below supplies those paths to renderer children only. Nothing is downloaded or
installed automatically. This new
streaming path and the complete explicit CLI conversion passed the sample test
with the latest resource bounds.

Do not publish these copies automatically. A human review is useful additional
evidence, but playback on
a device that ignores FEL cannot verify the enhancement picture contribution.

## Current research findings

The four approved source candidates were sampled without modifying originals.
Three excerpts carried FEL-labelled metadata but had no extractable enhancement
layer. That is a finding about the excerpts, not proof that the entire files lack
an enhancement layer. They must not be falsely certified as complete FEL inputs.
The confirmed layered source exposed a picture/RPU boundary mismatch in a simple
ten-second cut. Source-verified keyframe sampling is being tested; metadata
records are not discarded to hide the mismatch.

The first real-source research copy subsequently passed layer, track and timing
checks after an IDR-boundary excerpt was independently verified against the
source. All 246 displayed pictures had corresponding RPU records. The roughly
ten-second copy was 55.55% smaller, with HDR10 fallback scores of 95.10 mean and
92.21 fifth percentile. The subsequent full-sample native reconstruction
comparison also passed: 95.17 mean and 92.21 fifth percentile across all 246
pictures. Its source self-check passed at 99.25 mean and 97.43 fifth percentile.
These are sample results, not a forecast for the full file or other sources.

The shared sampler now reads primary first-slice NAL types to find IDR hints
after a CRA reference fails picture/RPU coverage. It requires one picture per
copied packet before deriving timestamps, ignores extra slices and enhancement
NALs, and still verifies source packet/picture/timing identity on every retry.
It neither deletes RPU records nor treats an IDR hint as preservation proof.

All 816 regression tests passed, and the helper recovered the same IDR timestamp
from the saved real-source evidence. No release has been deployed and no library
source has been replaced. File-size reduction remains a measured outcome, not a
promise.

### Native picture comparison and streaming integration

A portable, research-only FelBaker 1.0.0 / VapourSynth 73 setup now reconstructs
the enhancement picture on the Linux research host. A one-frame check succeeded
for both source and candidate. Replacing the enhancement pixels with zero changed
the rendered picture, confirming that this check was not merely reading the base
layer. This is a smoke test, not quality certification.

The completed all-246-frame comparison used separate lossless research renders
for the shared HDR metric. That was a reference experiment, not a practical
full-movie storage strategy. The new shared worker streams reconstructed frames
through pipes instead. Its all-frame source/candidate scores exactly matched
the lossless-render reference, without writing rendered media intermediates.
An initial two-input stall was resolved with bounded raw decoder/filter
threading. The latest follow-up also bounds the layer decoder's output/filter
pools and reaps child decoders on cancellation. The complete explicit CLI path
passed with these resource changes: combined native/fallback scores were 95.10
mean and 92.21 fifth percentile, with 55.55% size reduction and unchanged source.

The shared automatic selector now distinguishes MEL and FEL native metric
domains. It can evaluate FEL with the optional renderer; missing dependencies
are reported as such, not as an inherent GPU or media-format limitation. It
requires both complete native and fallback views and uses their weaker scores.
The ordinary automatic CLI also selected the candidate and completed full-copy
validation, with the same 55.55% reduction and originals retained. Deployment
and automatic source replacement are not authorized by these research results.

Whole-source trials now carry an output hash and can be reused after source and
output hashes are rechecked against their completed validation evidence. The
full-file quality and exact savings policy still apply. Partial excerpts cannot
use this shortcut. Runtime qualification passed: the same automatic sample run
dropped from 9m 1s to 4m 46s, with the same quality scores and 55.55% reduction.
This is a measured improvement for a whole-source trial, not a general speedup
claim for every movie or three-scene sample workflow.

A cancellation check observed both layer decoder children and confirmed they
were reaped after stopping the renderer. All 833 regression tests passed after
the whole-source reuse change; 839 passed after adding runtime staging. The policy revision
also allows old automatic skip decisions to be reconsidered on resubmission;
active work, explicit keep decisions and completed replacements stay protected.
The original media and production app remain unchanged. The NVIDIA encoder and the CPU research renderer are
different stages; this test does not establish GPU-accelerated FEL rendering.

Dependency provenance: [FelBaker upstream](https://github.com/bbeny123/felbaker)
and its 1.0.0 release. This portable setup is not yet bundled in the application.
Its [upstream license](https://github.com/bbeny123/felbaker/blob/main/LICENSE)
contains GPLv3 terms. Dependency licensing, source/notice delivery and image
packaging remain release-preparation work; no public binary redistribution has occurred.

### Reproducible optional runtime staging

`tools/install_fel_runtime.py` accepts the checksum-pinned upstream archives
listed in its `CHECKSUMS` map, plus FelBaker 1.0.0's `LICENSE` file. It checks
every archive before creating a fresh directory, preserves package notices,
checks the renderer library's hash, and loads the plugin to verify the setup.
It does not download anything or install host packages or drivers.

```sh
python3 tools/install_fel_runtime.py --archives /research/runtime-archives --destination /research/fel-runtime
python3 tools/install_fel_runtime.py --archives /research/runtime-archives --destination /research/fel-runtime --execute
```

The pinned build requires Linux x86-64, Python 3.12 and AVX2 CPU instructions.
These are dependency-build requirements, not a limitation of a video format or
NVIDIA GPU generation. The manifest checks Python/CPU compatibility before
loading the plugin. Library and Python search paths apply only to renderer
children, not the app or video encoder. The installer and all-frame comparison
passed on the isolated research host, without a parent library-path override.

The Dockerfile and context builder now include this runtime and its notices.
Future contexts require `--fel-runtime-archives`; no image has been built or
deployed. The image also requests NVIDIA `graphics` libraries for the other
native-DV Vulkan/EGL paths, as described in the
[NVIDIA container documentation](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/docker-specialized.html#driver-capabilities).
It does not choose a GPU or change host drivers.

### Current-image reader compatibility

The existing FFmpeg build reported changed picture parameter sets in a cut
excerpt, while its decode of the unchanged source was clean. That excerpt was
rejected, not excused. Shared DV reference preparation now falls back to the
complete source after a failed excerpt-recovery proof. Full source/output
checks still run; corrupt complete sources cannot inherit approval from a bad
sample. The end-to-end current-image-tools test passed using FFmpeg 8.0.1 for
both reading and NVIDIA encoding, without a driver change. Its 246-frame copy
went from 64,206,518 to 28,536,299 bytes (55.56% smaller). Enhancement-layer
payload, ordered RPU metadata, resolution, timing and copied tracks passed
preservation checks. The weaker native/fallback quality scores were 95.10 mean
and 92.20 fifth percentile; these are screening scores, not quality percentages.
The run took about five minutes and reused its fully validated whole-source
trial. This does not predict full-movie savings or runtime. All 840 regression
tests passed, including this fallback and packaging-input checks.

The source remained unchanged and the result is a separate copy awaiting
playback review. The runtime was qualified in the isolated research container;
the updated application image was subsequently built and qualified separately.
It passed automatic FEL conversion as non-root UID 568 with bundled runtime
discovery, producing a 55.56% smaller sample with the source unchanged. Generated
Profile 5 and MEL follow-up tests also passed in that same image. Nothing was
deployed; see [the qualification checkpoint](qualification-handoff.md).

### Mixed enhancement metadata and remaining renderer limits

The shared inventory now routes any sequence containing FEL frames through FEL
reconstruction, including a sequence that also contains MEL frames. It does not
call that mixture corrupt merely because two known enhancement types occur.
Ordered RPU semantics and enhancement payload must still match exactly between
source and output, and every frame must be reconstructed and checked. Missing
or unknown enhancement types remain an evidence error.

The isolated synthetic test alternated MEL and FEL records over all 246 frames
and passed native self/candidate comparison (candidate mean 95.41, fifth
percentile 92.67). No reconstructed intermediate media was written. Together
with the routing/evidence regressions, this verifies the mixed per-frame renderer
path, not full-file certification of every naturally occurring mixed title.

This matches the renderer's per-frame handling in
[FelBaker 1.0.0's RPU processor](https://github.com/bbeny123/felbaker/blob/1.0.0/src/RpuProcessor.cpp).
That dependency does have genuine implementation limits: reconstructed signal
depth up to 12 bits, enhancement depth up to 10 bits, and linear two-pivot NLQ
mapping. Its frame layout accepts 4:2:0 or 4:4:4 layers, with a same-size or
quarter-resolution enhancement layer. Unsupported inputs must report the actual
renderer failure; they must not be approved by disabling their residual signal.
These are renderer-build limitations, not NVIDIA generation exclusions.
