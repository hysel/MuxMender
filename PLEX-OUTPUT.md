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

- `Commando (1985) - NVIDIA HEVC - SDR - 31s.mkv`
- `Commando (1985) - NVIDIA AV1 - SDR - 31s.mkv`
- `American Sniper (2014) - NVIDIA HEVC - HDR10 - 32s.mkv`
- `American Sniper (2014) - NVIDIA AV1 - HDR10 - 32s.mkv`

All four SHA-256 values matched before and after moving. The destination contains
`playback-manifest.json` with the original output paths, current paths, sizes and
hashes. Validation evidence and reference clips remain in the project report
folder. Historical validation JSON retains the paths used during validation.

Plex library configuration and its automatic/periodic scan settings have not
been changed by this task. Add this directory to the intended Plex test library.
The validator still saves new runs in reports; publication to this playback
folder is a separate step after automated verification. Playback review is pending.
