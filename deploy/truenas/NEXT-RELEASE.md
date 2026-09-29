# Next release deployment checklist

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
