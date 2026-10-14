# Choosing compatible formats

MuxMender accepts supported video files, including MKV, MP4 and AVI. The container
extension alone does not determine whether a file can be converted. Video and
audio codecs, subtitles, HDR metadata, the assigned GPU and your player all matter.

For automatic encoding, allow only output codecs your players can handle. HEVC
and AV1 availability depends on the NVIDIA card, driver and image. Start with
**Create smaller copies** and test playback before using replacement.

Keep Original resolution to avoid deliberately resizing the picture. For HDR
or Dolby Vision, choose the intended preservation or SDR option when available.
If the selected route cannot pass its checks, MuxMender keeps the original and
shows a reason. It does not promise support for every profile or damaged input.

[Choose settings](wiki/Settings.md) · [Understand results](wiki/Results.md)
