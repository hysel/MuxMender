# Hardware acceleration

MuxMender prefers a detected GPU by default. It selects AMD AMF, NVIDIA
NVENC, or Intel Quick Sync when both the matching display adapter and FFmpeg
encoder are present. If no supported GPU is detected, it uses the CPU encoder.

```powershell
python python/muxmender.py "D:\Media" --execute --hardware auto
python python/muxmender.py "D:\Media" --execute --hardware amd
python python/muxmender.py "D:\Media" --execute --hardware nvidia
python python/muxmender.py "D:\Media" --execute --hardware intel
python python/muxmender.py "D:\Media" --execute --hardware cpu
```

## Requirements

- All modes require FFmpeg and FFprobe on `PATH`.
- AMD requires an AMD display driver and FFmpeg `hevc_amf`/`av1_amf`.
- NVIDIA requires an NVIDIA display driver and FFmpeg
  `hevc_nvenc`/`av1_nvenc`.
- Intel requires an Intel display driver and FFmpeg `hevc_qsv`/`av1_qsv`.
- CPU fallback requires FFmpeg `libx265` or `libsvtav1`.

The vendor SDKs are build-time dependencies and are not installed on an end
user's computer. When a driver or compatible FFmpeg build is missing,
MuxMender displays an official download link and, when possible, offers CPU
fallback. It never installs software without an explicit user choice.

## Failure behavior

Hardware encoding is monitored for forward progress. If it exits or makes no
progress for 20 seconds, MuxMender stops the complete FFmpeg process tree and
offers CPU encoding. Use `--hardware-stall-timeout` to change the timeout, or
`--hardware-fallback cpu` for unattended CPU fallback.

The VS Code extension presents **Use CPU** and **Download / Install** buttons.
The latter opens the relevant official FFmpeg or GPU-vendor download page.
Original media files are never deleted or overwritten by the extension.

## Resolution policy

Resolution is preserved by default. In `--resolution keep` mode MuxMender adds
no FFmpeg scaling filter and rejects an output whose dimensions differ from the
source. Users may explicitly select `2160p`, `1080p`, `720p`, or `480p` as a
maximum resolution. These ceilings preserve aspect ratio, use even dimensions,
and never upscale a smaller source.
