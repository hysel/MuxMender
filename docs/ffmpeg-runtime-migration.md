# FFmpeg 9 runtime cleanup

New app builds use the pinned FFmpeg 9.0.2 source build on a clean Ubuntu
base, without an inherited FFmpeg 8 command-line fallback. Standalone and
HDR10+ container recipes and the NVIDIA preflight use the immutable v61
FFmpeg 9 app runtime. No installed container is changed by these edits.
The reused v61 image still includes its previously qualified custom reader;
switching the command-line runtime does not rebuild that separate executable.
Replacing it remains part of the fresh reader qualification below.

The custom reader build and packaging now require FFmpeg 9.0.2 sources.
Build it and repeat reader qualification before supplying a new bundle.
Old binary receipts cannot certify the new reader. The specialized recipes
still need new image smoke checks before release.

The candidate now pins PyAV 19.0.0's CPython 3.12+ Linux wheel. Its checksum
was verified against the package index and an isolated Linux import reported
FFmpeg 9 ABIs: avcodec/avformat/device 63, avutil 61, avfilter 12,
swscale 10 and swresample 7. The isolated audio/HDR suite subsequently passed
71 tests without skips; a successful import alone is not media qualification. Standalone users
installing this optional dependency need Python 3.12 or newer.

## Complete-image qualification

Release-material follow-up verified all 30 PyAV 19 bundled library code
sections: 24 match the upstream 9.0.2-1 runtime and six match the pinned
distribution packages. All 20 upstream source archives passed their recipe
checksums. Sixty-one original notice files were extracted as a draft subset.
Exact-image OS source collection completed for 111 package versions. The missing
superseded package was recovered from its checksum-verified source descriptor;
its descriptor signature has not been independently verified. Final source-bundle
and notice review remain pending. Old wheel notices cannot substitute for this
release's materials.

The final isolated run passed on 2026-10-12. Candidate image identity:
`sha256:067a847ceba0dbd189ad95be8a815442a7373389b9822ad59a888f0b26c020cf`.
The audit reported no version mismatches: FFmpeg, FFprobe and the CUDA reader
reported 9.0.2; PyAV 19 loaded all seven FFmpeg 9 library ABIs. Runtime checks
passed 229 tests with ten skips; all ten generated GPU tests passed. Safe-copy
creation, retained-copy history after container recreation, active-stage
cancellation and cancelled history after recreation each passed. Generated
sources remained unchanged. Orphan-process reaping passed as well.

This is a private candidate, not a published release. New dependency source
notices and release review are still pending. These lifecycle checks do not
certify resuming an active encode at the same frame during an upgrade, and
the ten skipped tests are coverage gaps, not passes.

The first native image built successfully and passed the executable/PyAV
FFmpeg 9 audit. The packaged suite ran 239 tests: one errored because the
launcher omitted `/work`, and ten were skipped. The launcher now mounts a
UID-568 private temporary workspace for runtime and GPU smoke checks; a
regression assertion covers both mounts. The final run above resolved this. This was a
harness failure, not proof that the media checks passed.

The corrected run passed 229 packaged tests with ten skips and the reaper
check. GPU preflight then stopped on HTTP 403: the launcher used an unapproved
loopback Host value. The allowed `truenas` endpoint was verified from the host
with a fresh, idle queue and is now used by the launcher. GPU/lifecycle checks
passed in the final run above; this correction does not weaken host validation.

`deploy/truenas/qualify-ffmpeg9-native.sh` builds a separate clean-base image,
audits executable and PyAV library versions, runs packaged regressions and
reaper checks, then checks generated GPU encoding, safe-copy processing and
cancellation across container recreation. It checks production is idle before
GPU work, never mounts the library, and never updates the installed app.
The systemd-launched run survives the initiating shell closing. A successful
run is not publication approval or certification of an active-job upgrade.

The three custom-reader source patches applied successfully in memory to the
checksum-verified 9.0.2 source. The isolated build succeeded; its SHA-256 is
`bddf0a900a6ebc55fe50adae5fb0eea4fc430ab886f0ec0b9fdcf11a2c4a5fe2`.
Generated HEVC and AV1 GPU-reader checks passed with exact frame/HDR metadata
checks and no corruption false passes. These short fixtures do not replace
representative full-file qualification or certify every HDR format.

PyAV 19 with the FFmpeg 9 executable passed 71 tests across 11 audio/HDR modules
in isolated Linux, with zero skips. Production is unchanged. The native image
passed qualification above, but the final image containing subsequent resource
and UI changes still needs its own qualification and refreshed release materials.
Image smoke checks now reject an older reader or PyAV codec ABI.
`audit_image_runtime.py --require-ffmpeg9` checks all inventoried reader banners
and every loaded PyAV FFmpeg library ABI.

Historical baseline comparison tools and evidence remain accurate and isolated.
The existing release-material archive describes the old wheel and must not be
reused for this candidate. Collect and verify new wheel library sources and
notices before publication; do not rename old archives to imply new provenance.
