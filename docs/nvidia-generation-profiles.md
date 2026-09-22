# NVIDIA generation hints and verified capabilities

The shared automatic engine uses NVIDIA architecture hints to order trials:
Ada/Blackwell try AV1 first; older or unknown adapters try HEVC first. Both
eligible codecs are still tested. An architecture hint never rejects a codec,
changes source geometry, lowers quality thresholds, or certifies metadata.

Discovery records the GPU UUID, name, driver, memory and compute capability.
Older `nvidia-smi` versions fall back to discovery without compute capability.
Missing telemetry is not proof that encoding is unavailable. Multiple visible
GPUs use neutral ordering and fresh probes; explicit per-GPU scheduling is a
separate future feature, not implemented by these profiles.

Successful synthetic initialization checks can be reused for 24 hours. Keys
include the single visible adapter's identity/driver, FFmpeg path/build/file
identity, visibility environment, encoder, exact dimensions and pixel format.
Unknown and multi-GPU configurations are not cached. Failures/timeouts are
never cached. Corrupt, expired or unwritable caches fall back to a real probe.
This cache only accelerates initialization checks: real sample encoding,
quality scoring, metadata preservation and full-output validation still run.
It is not a guarantee that a previously working GPU is currently free.

The app shares its small `.gpu-capabilities` JSON cache on the output mount.
Standalone automatic jobs default to that folder under their output directory;
`--capability-cache-dir` may specify a common cache across standalone jobs.
CLI and TrueNAS both invoke the same engine and probe service.

No automatic driver installation or CPU encoding fallback was added. Existing
shared-host resource admission and encoder quality presets remain unchanged.
Generation-specific preset tuning needs measured quality/speed evidence; the
generation table is not a reason to assume that one CQ value is equivalent
across cards.

Reference: https://docs.nvidia.com/video-technologies/video-codec-sdk/13.1/nvenc-application-note/index.html

## Results controls

Results search, filters, batch selection and sorting are inside a native
keyboard-accessible disclosure. It starts open and can fold without hiding
result cards or clearing selections. Polling does not recreate the disclosure.
Existing dark-mode, focus and forced-colors styles apply.

## Verification

Generated/mocked regression coverage includes architecture hints, old/missing
telemetry, cache reuse/invalidation, corrupt/expired cache, transient failures,
unknown/multiple adapters, CLI/app argument parity and disclosure structure.
This does not constitute hardware qualification of every NVIDIA generation.
