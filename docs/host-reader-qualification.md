# Keeping private GPU reader qualification across image updates

This describes unreleased integration work, not a setup step for the published
v60 image. GPU encoding and GPU-assisted frame validation are separate features.

The public image must not contain a user's GPU UUID or a receipt that pretends
to qualify every server. Instead, the next loader can use a private host receipt
at `/opt/muxmender-host-qualification/qualification.json`. An administrator can
provide this as a read-only mount from a persistent host directory outside the
media and output folders. The directory and file must be owned by root, must not
be group/world writable, and must not be symlinks. Never use an app-writable
output directory for this mount.

The executable still comes from the image at `/opt/muxmender-readers/ffprobe-cuda`.
The loader checks its SHA256 against the receipt, and checks the visible GPU,
driver and device selection. A changed binary or driver requires evidence for
that changed configuration; an image update with identical reader/runtime
bindings can keep using existing evidence. Image-owned receipts remain supported
for older private builds. A missing or mismatched receipt keeps complete CPU
inspection; it does not skip validation or reject the source.

Each receipt scope applies only to its tested codec, pixel format and SDR/HDR
mode. HDR results do not enable SDR. Every-frame evidence, corruption rejection
and a measured benefit are needed before adding a scope. Qualification does not
approve output quality, savings or source replacement; those checks still run.
Generated SDR experiments alone do not qualify a scope. The measured AV1 8-bit
SDR Matroska scope has full-source evidence and passed an isolated public-image
runtime check with the updated shared code and private host receipt. Other SDR
scopes still need full-source evidence. The final release image needs its own
smoke check; this research did not enable the receipt in production.

The unreleased `deploy/truenas/install_reader_qualification.py` installer takes
an existing qualified bundle with its executable, receipt and complete evidence.
It derives the allowed scopes again rather than trusting their labels. Its
default destination is `/var/lib/muxmender-reader-qualification`. Installation
requires Linux administrator access and trusted root-owned parent directories;
the receipt is written atomically with mode 0444. An identical receipt is a
no-op. A different receipt requires an explicit `--replace` after review.
The installer does not modify app mounts, start containers or touch media.
After release qualification, the host directory will be mounted read-only at
`/opt/muxmender-host-qualification`. Do not install generated-only SDR evidence.

When the production workflow chooses a reader, progress identifies CPU or GPU.
That dispatch and the measured whole-task time—not just GPU visibility—are the
evidence that an optimization is actually being used.
