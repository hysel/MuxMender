# MuxMender for VS Code

This companion extension streams MuxMender analysis into a dedicated
`MuxMender` channel in VS Code's **Output** panel.

Run **MuxMender: Scan Media Folder (Dry Run)** from the Command Palette and
choose a media directory. The extension deliberately exposes only the safe,
read-only scan command for folders.

Run **MuxMender: Optimize Selected Media File (Safe Copy)** to choose one media
file. A VS Code progress notification tracks the conversion while detailed
FFmpeg output streams to the `MuxMender` Output channel. The optimized file is
written under the workspace's `test-output` directory. The source file is never
deleted, renamed, moved, or overwritten, and the extension provides no option
that can enable original-file deletion.

Hardware mode defaults to `auto`, which prefers a detected AMD, NVIDIA, or
Intel GPU. Change `MuxMender: Hardware` in Settings to force a vendor or CPU.
If a required driver or FFmpeg encoder is missing, the extension offers an
official **Download / Install** page. If hardware encoding fails or stalls, it
offers **Use CPU** and never retries or installs software without a click.

Resolution defaults to `keep`, which adds no scaling filter and verifies that
the output dimensions exactly match the source. Optional 2160p, 1080p, 720p,
and 480p ceilings must be selected explicitly; they preserve aspect ratio and
never upscale smaller videos.
# Native preview progress (0.6.0)

After installing this update, reload the existing VS Code window to activate it.
Run **MuxMender: Preview Dolby Vision Color (Safe Native Test)** and select one
profile 5 file, then HDR PQ or SDR output. The three-second preview starts at
five minutes, keeps source dimensions, and writes a new timestamped test-output
folder. It is video-only, not a complete media optimization.

The same native process writes to the MuxMender Output channel and updates the
notification progress bar. Chunk-split progress markers are buffered correctly.
Originals and existing outputs are never deleted or overwritten by this path.
