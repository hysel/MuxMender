# Publish an app image

The manual workflow is prepared, not enabled or exercised. No public GHCR image
has been announced. Do not use a production TrueNAS host as the Actions runner.

## Outstanding requirements

1. Provision a disposable Linux amd64 NVIDIA runner with Docker, Python 3.12 and
   GitHub CLI. Label it `muxmender-release-nvidia`. Limit it to this repository;
   don't allow untrusted pull requests to execute on it.
2. Create the `container-release` GitHub environment with required approval and
   main-only deployment rules. Verify these settings before enabling the workflow.
3. Prepare a clean context using the existing shared release packager. Add complete
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
