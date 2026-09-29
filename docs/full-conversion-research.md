# Full conversion research app

This separate Docker app measures complete copies when short trials have not
qualified a setting. It does not replace the production app or change its queue.

It uses the same encoder, source inspection, metadata, track, timing and quality
checks as the regular workflow. Sample rejection remains in the report. Full
copies are measured with the existing mean and fifth-percentile VMAF floors of
90, and the existing size-aware savings policy. VMAF is not a percentage of
quality retained. HDR comparisons use the existing common rendering domain.

Every result is research-only and cannot authorize replacement. A failed check
does not become a pass just because encoding completed. Unlike normal rejected
outputs, these explicitly requested research copies remain for inspection.
Source writes are never allowed. Automatic cleanup removes intermediate work
after the task; the explicitly requested research output and summaries remain.

Build `deploy/truenas/Dockerfile.full-research` with `BASE_IMAGE` set to the
existing local app image. Mount the same source dataset at `/media` **read-only**,
a fresh dedicated research directory at `/output` writable, and a private case
manifest at `/config/cases.json` read-only. Grant the container NVIDIA access.
Keep the production queue paused during the experiment on a shared GPU.

The manifest is a JSON list of `id`, `source` (absolute container path), and `cq`
(integer 18–32). Never commit a manifest containing actual media names. Each case
runs once, serially, with AV1 NVENC, p7, HQ, 32-frame lookahead, full-resolution
multipass and a 200 Mbps ceiling. These are research settings, not qualifications.
There is no CPU fallback, resizing or frame-rate conversion.

Set `MUXMENDER_ALLOWED_HOSTS` to the dedicated dashboard hostname/IP and published
port. Container port is 8765. The dashboard stays available after completion.
Each case has a launcher log, tracked progress, exit record, and an `auto-*`
directory containing sample selection and full result evidence. All output
copies occupy additional space; none count as reclaimed library space.

Stopping interrupts the current case. Restarting does not rerun submitted cases,
including interrupted ones. Use a **new output directory** for a deliberate retry;
do not remove the submission markers of an active run. Keep at least 50 GiB free
in addition to space for retained copies and validation artifacts.
