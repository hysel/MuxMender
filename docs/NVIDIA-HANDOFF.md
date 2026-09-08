# Hardware validation and main-repository handoff

## Current implementation

Intel AV1 HDR10 now uses the shared repair, ordered mux and independent full-file
verifier through the normal standalone CLI. Dolby Vision preservation is opt-in
for AMD/Intel Profile 8.1; default DV behavior remains skip. NVIDIA DV remains a
separate research route. See [HARDWARE.md](HARDWARE.md) for exact tested scope and
[STANDALONE.md](STANDALONE.md) for commands. Unsupported metadata and failed
preservation/savings checks block publication; source files remain untouched.

No new scripts were added for Intel integration. Reusable behavior stays in:
- `python/muxmender.py`: normal CLI dispatch, release-preserving rename plans,
  video-only outputs, cleanup commands and per-run savings.
- `python/mux_integrity.py`: ordered mux, seek checks, bounded AV1 metadata repair.
- `python/validate_nvidia.py`: actual generated tests, HDR research and full verifier.
- `python/dv_full_file.py` and `python/dv_preservation_test.py`: shared full/sample DV.
- `python/library_planner.py`: inventory and reviewed NFO/sample cleanup plans.
- `python/runtime_support.py`, `job_tracking.py`, `dashboard.py`: memory guards,
  terminal/dashboard stage progress, recent-rate ETA and stale-job handling.

Runtime Python stays in `python/`, shared design in `python/ui/`, Windows helpers
in `powershell/`, and guides in `docs/`. Keep the root small. Preserve the approved
control-room design and stationary progress bars. No VS Code dependency, editor
reloads or new windows are required. Metadata enrichment remains roadmap work.

## Validation

193 unit tests pass. Actual Intel fixtures passed eight SDR/PQ/irregular-timing
cases across HEVC/AV1. Integrated CLI regressions passed 829 AV1 HDR frames at both
transparent and balanced settings and 960 DV frames, with source preservation,
HDR/RPU checks as applicable, full decode and seeking. Video-only output was
checked to contain just its video, with recovery data outside the output folder.

Full Intel No Time to Die AV1 HDR10 (58.13% smaller) and House of the Dragon S03E02
HEVC DV 8.1 (35.50% smaller) passed Chrome/Sony TV review and Y-backed playback.
Earlier approved Intel SDR and HEVC HDR10 and NVIDIA results are summarized in
HARDWARE.md. These approvals do not certify every GPU, driver, media file or client.
The bounded regression is not a new full-file encoding or new visual-quality test.

Evidence lives locally under `reports/` and is intentionally excluded from Git.
Start with `reports/overnight-readiness-20260907.json` and the integration reports
listed in HARDWARE.md. Some historical intermediate paths were intentionally
removed during authorized cleanup; final test videos and evidence were retained.

## Media state and permissions

Only the two approved Intel replacements were written to their original Y folders
on September 8, keeping release filenames. The user approved Y playback and then
separately authorized deletion of their two original backups. Fresh replacement
SHA-256 checks passed before removal. No other Y content was changed in that task.
Net savings for the pair: 13.899 GB (50.82%). Prior one-file replacement/deletion
permissions do not grant future blanket access to change or delete Y media.

The five local Plex test videos remain in `C:/MuxMender-Plex`. No further playback
review is pending for the two approved full outputs. Automatic source deletion
and overwrite remain disabled in the product. Cleanup is preview-first, scoped,
explicitly confirmed, and protects primary video and subtitles at every depth.

## Continuing development

The user authorized committing, pushing and merging this integration into main.
Use remote main for the other agent after synchronization; do not copy ignored
media, reports, portable tools or credentials into version control. Preserve any
unrelated work in the other checkout. Future Git actions follow session permission.

Next priorities: AMD regression against the shared mux/seek fixes, optional metadata
enrichment for both Plex and file tags, broader hardware/client coverage, and
separate TrueNAS/Linux validation. The browser workflow still limits its queue to
its validated SDR path; CLI HDR/DV support does not silently expand Web UI policy.
