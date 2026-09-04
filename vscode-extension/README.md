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
