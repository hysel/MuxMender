# Publish an app image

The manual workflow is prepared, not enabled or exercised. No public GHCR image
has been announced. Do not use a production TrueNAS host as the Actions runner.

## Outstanding requirements

**Public image blocker:** the upstream Dockerfile for our current LinuxServer
base enables FFmpeg `--enable-nonfree` alongside GPL components and libfdk_aac.
The app image retains that FFmpeg 8 fallback. Our separate FFmpeg 9 build does
not make the inherited binary redistributable. Do not publish the current image.
The workflow now inventories the actual binaries and refuses that configuration.
Use a clean, redistributable runtime base and requalify its dependency loading,
fallback behavior, service and GPU before public release. Deleting a binary in a
later Docker layer is not a solution: its old layer would still be distributed.

Source: [upstream base build recipe](https://github.com/linuxserver/docker-ffmpeg/blob/8.0.1-cli-ls61/Dockerfile).
Exact digest runtime inspection is still required; a tag's source recipe is not
substituted for inspecting the binary actually shipped.

The clean-base candidate is `deploy/truenas/Dockerfile.public`. It builds the
same FFmpeg 9 recipe on pinned Ubuntu and copies the same app code. It isn't
image-qualified yet; in particular the packaged GPU reader's dynamic libraries
may need additional clean-base packages. The production Dockerfile is unchanged.

TrueNAS may run an administrator-launched, isolated candidate build instead of
hosting an Actions runner. `launch-public-candidate.sh` uses a separate context
and image, survives shell timeout and mounts no library media. Generated GPU
checks require a fresh idle production queue snapshot. This is research, not
permission to publish an incompletely reviewed image. No permanent Actions
runner is installed on the shared production host.

The first clean-base candidate passed runtime and generated NVIDIA checks. The
next isolated package checks service startup, browser/API responses, cross-site
write rejection, an inspection of a generated clip and retained history when
moving from the installed image to the candidate. It also collects exact Ubuntu
source packages and version-matched upstream archives. These checks and source
collection do not authorize public distribution: missing package versions,
transitive Rust/conda dependencies and the wheel's bundled libraries still need
their corresponding source and review.

1. Provision a disposable Linux amd64 NVIDIA runner with Docker, Python 3.12 and
   GitHub CLI. Label it `muxmender-release-nvidia`. Limit it to this repository;
   don't allow untrusted pull requests to execute on it.
2. Create the `container-release` GitHub environment with required approval and
   main-only deployment rules. Verify these settings before enabling the workflow.
3. Prepare a clean context using the existing shared release packager, adding
   `Dockerfile.public`, the repository LICENSE and the current smoke script. Add complete
   third-party notices, corresponding source and build instructions. Review the
   base image, apt packages, PyAV wheel, FFmpeg, HDR tools and FEL runtime—not just
   MuxMender's MIT license. Use the inventory below as a starting point, not a legal
   compliance certification.
4. Review embedded reader evidence for private paths and identifiers. Don't alter
   a qualification receipt to pretend another GPU has been qualified. The current
   receipt is hardware-bound; other GPUs need their own qualification or CPU fallback.
5. Add `public-release.json` to the context. It records schema 1, exact version,
   full revision, `redistribution_reviewed: true`, `privacy_reviewed: true`, and
   `materials`: objects containing `role`, relative `path` and SHA256. Include
   roles `app-license`, `third-party-notices`, `corresponding-source` and
   `build-instructions`. The audit verifies these files; a declaration does not
   replace an actual licensing or privacy review.
6. Upload the reviewed `public-context.tar` to a GitHub Release and supply its
   checksum to the manual workflow. Keep that source material available with the
   final release. Public release assets are public: review before uploading.

The workflow accepts only main and checks its app version and source revision.
It rejects unsafe archive entries, checks materials, compares app code/tests/build
files with the checkout, builds once, runs runtime and NVIDIA checks, then pushes
that exact image. It refuses to overwrite an existing version. Registry errors
other than a missing tag stop publication.

## Redistribution inventory: initial review

| Component | Finding | Remaining work |
| --- | --- | --- |
| MuxMender | MIT license in repository | Include license in distributed image/materials. |
| FFmpeg 9 custom build | GPL and version3 enabled; source archives pinned | Preserve source, build options, dependency source and GPL notices. Check generated configuration for nonfree flags. |
| Base image and FFmpeg 8 fallback | Pinned third-party image; separate build | Inventory its libraries and obtain matching source/build materials; our FFmpeg 9 source isn't a substitute. |
| Custom GPU reader | Patched FFmpeg 8 with source and notices | Review complete build reproduction and private qualification evidence. |
| dovi_tool / hdr10plus_tool | Upstream MIT licenses | Bundle version-matched notices and review transitive dependencies. |
| FelBaker 1.0.0 | Upstream GPLv3, notice includes derived work | Supply corresponding source/build materials and review dependency obligations. |
| PyAV / bundled libraries | Pinned wheel with upstream notices | Inventory wheel contents and corresponding-source obligations. |
| OS / conda runtime libraries | Multiple licenses, some notices packaged | Inventory exact installed versions and retain applicable source/notices. |

References: [FFmpeg licensing](https://ffmpeg.org/legal.html),
[FelBaker license](https://github.com/bbeny123/FelBaker/blob/1.0.0/LICENSE),
[dovi_tool license](https://github.com/quietvoid/dovi_tool/blob/2.3.3/LICENSE),
[hdr10plus_tool license](https://github.com/quietvoid/hdr10plus_tool/blob/1.7.2/LICENSE).
This is an engineering inventory, not legal advice or completed clearance.

## Before announcing a release

The isolated installation harness uses generated media and an explicit
keep-original decision to check API access, cross-site write rejection, retained
history after upgrading, source preservation and clean shutdown. It does not
exercise a processing worker or bypass resource admission. Runtime regression
and generated GPU encoding smoke checks are separate; full safe-copy lifecycle
and public installation checks are still needed.

Dependency review also includes what is inside prebuilt packages. The PyAV wheel
bundles its own FFmpeg and other native libraries; collecting PyAV's Python source
alone is not enough. Keep its embedded library inventory, upstream build recipes,
patches and matching dependency sources together. Configure flags are evidence,
not a substitute for reviewing the actual licenses.

`tools/stage_conda_materials.py` retains recipes, patches and licenses from the
checksum-pinned FEL packages without loading them. It requires Python 3.14 and
PyYAML as offline tooling, not as app dependencies. `tools/inspect_wheel_materials.py`
inventories a pinned wheel and reads upstream recipes as syntax trees without
executing them. `tools/fetch_pinned_materials.py` downloads checksum-pinned public
archives and records its progress on the development dashboard. These tools do
not grant redistribution approval, process videos or change the installed app.

Public contexts exclude private GPU reader receipts and research evidence. The
GPU can still encode with NVENC; the accelerated HDR frame-inspection reader
requires a trusted, host-specific qualification receipt. Without one, the shared
workflow uses its existing complete CPU reader. Do not copy another host's receipt
or remove validation checks to enable acceleration.

Rust lockfiles are also included in source review. `tools/prepare_rust_source_pins.py`
reads them without running Cargo, and `tools/audit_crate_notices.py` retains license
metadata and notices from checksum-verified crate archives. A missing notice file
remains an explicit review item; a license declaration alone is not approval.

Notice discovery also retains original source-file license headers and AUTHORS
files. When a crate omits its notice file, `tools/recover_crate_notices.py` makes
read-only GitHub requests at its recorded source revision. A manual revision
requires a separate source comparison and keeps its qualification limits in the
receipt. These records distinguish finding notice material from approving the
license terms for publication.

Make the GHCR package public intentionally. Public containers can be pulled without
credentials; confirm that with a clean Docker configuration on a separate machine.
Record the registry digest, inspect the SBOM/provenance and dependency scan, and
perform a clean TrueNAS install using `deploy/truenas/compose.release.yaml`.
The present workflow does not yet generate SBOM/provenance, scan dependencies or
test the browser/API service lifecycle; these remain release-readiness work.

Check source browsing, a safe-copy job, retained history after an image update,
cancellation, permissions and the host-port portal link. Don't replace source
media during installation testing. Public download and installation claims must
wait for these checks.

## Rollback

Pause new starts, let active work finish and preserve both mounted directories.
Select the previous known-good image version, then verify history and queue state.
If a release changes stored-state formats, document its rollback procedure before
shipping. Don't delete history, work directories or library files to roll back an image.
