# Permanent local Plex playback folder

The user selected this local server, explicitly excluding Y:.

**Playback folder: `C:\MuxMender-Plex`**

Use this same folder for future validated samples intended for user playback.
Only publish successful, separately generated playback outputs here, with unique,
descriptive movie/codec/color names. Never put original media, intermediate
references, failed outputs or logs in the Plex media inventory. Never overwrite
or automatically clean up an existing playback file.

On 2026-09-05, the user authorized moving the four successful samples from
`reports/nvidia-validation-20260905-175901-0b2fe5b8/` into this folder:

- `SDR test video - NVIDIA HEVC - SDR - 31s.mkv`
- `SDR test video - NVIDIA AV1 - SDR - 31s.mkv`
- `HDR test video - NVIDIA HEVC - HDR10 - 32s.mkv`
- `HDR test video - NVIDIA AV1 - HDR10 - 32s.mkv`

All four SHA-256 values matched before and after moving. The destination contains
`playback-manifest.json` with the original output paths, current paths, sizes and
hashes. Validation evidence and reference clips remain in the project report
folder. Historical validation JSON retains the paths used during validation.

Plex library configuration and its automatic/periodic scan settings have not
been changed by this task. Add this directory to the intended Plex test library.
The validator still saves new runs in reports; publication to this playback
folder is a separate step after automated verification. Playback review is pending.

## Intel playback tests

Local server: `haven42WinIntel`, library `Other Videos`, folder `C:/MuxMender-Plex`.
Use `Playback Test` in local test filenames, not the word `sample`: Plex excludes
small files with that keyword. Verify actual indexed items after requesting a scan.
Current tests: Borderlands (2024) Intel HEVC/AV1 SDR and Intel HDR case A (2021)
Intel HEVC HDR10. Source media on Y is unchanged.
