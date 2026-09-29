# Let the source guide the conversion

We should try a compatible encoding path rather than reject a video just because
its format was absent from an earlier test collection. Admission is not approval
to replace the original: the output still has to pass quality, timing, track,
metadata and savings checks.

## Implemented, awaiting deployment

- The first moving video is the primary track. Cover artwork is not mistaken for
  the movie. Other moving video tracks are copied and their packets checked.
- Moving artwork to Matroska attachments keeps stream metadata and dispositions
  attached to the right tracks.
- Missing artwork filename/MIME labels no longer block admission. Container
  labels are derived from the image codec; existing labels and image bytes are
  preserved. A generated MP4 with an unlabelled JPEG cover passed full shared
  validation after conversion to Matroska attachments. Embedded filenames are
  never used as filesystem paths.
- The shared hardware finalizer replaces only the primary video and retains the
  other source tracks, rather than requiring exactly one video stream.
- Pixel formats reach runtime capability trials instead of a short historical
  allowlist. Unknown or malformed format labels are still reported as errors.
- Known interlaced SDR can reach capability trials. Field order and cadence must
  survive; this does not enable automatic deinterlacing or certify every encoder.
- Consistent decoded HDR labels can fill missing container labels. Conflicting
  declarations are not silently overwritten, and full-frame validation remains.

## Evidence and limits

A read-only library scan inspected 11,455 files. It found examples of multiple
video tracks, interlacing, unusual pixel formats, missing color labels and Dolby
Vision Profiles 5, 7 and 8. Category counts overlap and are not failure counts.

The remote regression suite passed all 736 tests with no skips after providing
an isolated JavaScript runtime and the CLI package manifest. A generated two-video
fixture also passed full shared validation after primary-track encoding, and
again after shared hardware finalization. This confirms track preservation,
not visual quality or savings on arbitrary sources.

Profile 8.1 qualification must not be described as qualification of Profiles 5
or 7. Those profiles need their own color and enhancement-layer handling. The
legacy vendor-specific Dolby Vision routes remain separate from the qualified
NVIDIA workflow. No production image was deployed as part of this audit.

The NVIDIA Profile 8.1 sample/full workflow passed a generated 45-second,
540-frame two-video fixture with a 2.5-second start offset. Full validation
preserved the secondary video packets, audio, timing and Dolby Vision metadata.
CQ18 reduced the generated file size by 59.96%; its bounded HDR common-render
quality scores were 98.74 mean and 95.98 fifth percentile. CQ24 correctly stopped
before full encoding because its quality scores fell below the floor. These are
synthetic workflow checks, not estimates of library savings or a native Dolby
Vision perceptual certification. The shared adapter now requires additional-track
packet evidence for both sample admission and full-output acceptance.

The ordered DV workflow now restores a nonzero source start on the reconstructed
video only; original audio and subtitle timestamps are not shifted. A generated
24-frame Profile 8.1 fixture starting at 2.5 seconds passed decoded timeline,
per-frame DV metadata and copied audio packet comparisons. The fixture uses the
same no-B-frame structure as the qualified NVIDIA encoder path. This is not
evidence for arbitrary variable-frame-rate reconstruction. The test is reproducible
with `tools/smoke_dv_timing.py` on the Linux research server.

The DV adapter, inner full-file service and publisher use the original exact byte
target, not a floating-point percentage round trip. Fixed targets also use exact
rational arithmetic, with one-byte boundary regression coverage. CLI packaging
includes the new savings, source-format and DV track modules; the manifest parity
test checks every runtime module rather than relying on source-tree imports.

Four files could not be opened on repeat inspection because their Matroska EBML
headers were invalid. That is an input-read failure, not an arbitrary format
gate. They were left untouched.

## Further hardware investigation

On the tested NVIDIA card, four-frame interlaced HEVC and AV1 initialization
failed, while H.264 initialized. A separate generated H.264 test preserved all
25 frames, presentation timestamps, interlace flags and top-field-first order.
This is evidence for investigating an H.264 fallback, not automatic approval to
deinterlace or switch a user's allowed codecs. Full quality and savings trials
are still needed.

The first Profile 5 rendering probe silently used Mesa's CPU renderer. Selecting
the installed NVIDIA EGL Vulkan driver for that research process allowed a
Profile 5 frame to render on the RTX 5050. This did not change container or host
configuration. The generated-only `tools/probe_dv_renderer.py` records the actual
device and does not mistake successful software rendering for GPU availability.
It does not certify re-encoding or perceptual quality.

The development observer now reports the latest tracked job from each configured
research root. A newer completed test must not hide an older running test on the
same machine. Its regression test runs on Linux, not the workstation.

NVIDIA documents the [headless EGL Vulkan driver alternative](https://download.nvidia.com/XFree86/Linux-x86_64/460.27.04/README/installedcomponents.html)
and the [graphics container capability](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/docker-specialized.html).
Any eventual production renderer should use supported container configuration
and verify the selected device, rather than rely on a research-only driver file.

Four sampled Profile 7 inputs declared that profile in the container but their
decoded sample frames contained BT.709 labels and no observed Dolby Vision RPU.
Sampled absence does not prove whole-file absence. Do not discard a Dolby Vision
declaration or enhancement layer from this evidence alone; inspect the bitstream
before deciding whether those inputs contain inconsistent container metadata.

A subsequent 120-picture elementary-bitstream sample from each of those four
inputs contained only base-layer NAL units, no RPU NALs, and yielded no RPU data
with the independent extraction tool. This strengthens the inconsistent-header
diagnosis but is still bounded evidence, not permission to remove a whole-file
Dolby Vision declaration.

For one of those inputs, a subsequent complete 4.28 GB primary-video bitstream
inventory found no RPU or enhancement-layer NAL units. The source stat was unchanged
and demuxing completed without errors. The bounded-memory reader was tested at
every chunk boundary and against a generated positive control containing 540 RPUs.
The scan took about nine seconds without GPU decoding. This establishes a stale
DV container declaration for that inspected stream, not general permission to
ignore DV labels. Shared automatic recovery now requires fresh per-file evidence
and the ordinary decoded color, timing, quality and track checks. Real RPU or
enhancement-layer presence stops this check early and retains the DV route.

Generated stale-label fixtures passed the complete shared automatic workflow for
both HDR and BT.709 SDR, with validated copies about 72.18% and 72.19% smaller.
The HDR finalizer independently rechecks its current source bitstream rather than
trusting an inherited routing flag. Sources are not rewritten. These synthetic
savings do not predict the saving of the inspected library file.

The first generated fixture also exposed a separate long-GOP reference-sampling
failure. The planner now considers complete keyframe pairs, including a preceding
group when it covers the requested scene. Verification expands to include its
video and audio packets; it still requires exact source pixels, timestamps and
packet identities. The same roughly 20-second-GOP multi-video fixture subsequently
passed the full shared HDR workflow, producing a validated copy 61.51% smaller.
This is synthetic evidence, not a prediction of library savings. The consolidated
remote regression suite passed 736 tests without skips after this change.

An explicit-timestamp path passed a generated 24-frame variable-rate DV fixture
at a 2.5-second offset, then the NVIDIA sample/full workflow passed a 540-frame
variable-rate fixture with a secondary video track. The full result preserved
every decoded timestamp, DV metadata, static HDR and copied track. Its generated
size reduction was 57.55%; the 309-frame sample quality scores were 99.01 mean
and 96.38 fifth percentile in the common HDR10 rendering domain.

Variable-rate samples are selected by elapsed decoded time, not nominal FPS.
Packet-to-picture coverage must be complete before admitting the variable clock;
truncated GOPs cannot silently become VFR evidence. The reconstructed stream uses
explicit decoded timestamps. Nominal frame-rate labels may differ only after
complete decoded timing/count validation; geometry and metadata checks remain.
Legacy non-experimental routes retain their existing restrictions. These generated
checks do not certify every input cadence, enhancement layer or GPU vendor.
