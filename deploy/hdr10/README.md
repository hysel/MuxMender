# Static HDR10 trial, not automatic replacement

This standalone container reuses the previously built HDR10+ tool image.
It tests three short excerpts of HDR quality case A using NVIDIA HEVC CQ22,
without changing resolution, frame cadence, color tags or the original source.
Chroma location is explicitly requested and checked on decoded frames.

Each output is remuxed with the reference timestamps, track metadata and copied
audio/subtitles. The validator requires exact static HDR metadata and rejects
dynamic HDR/Dolby Vision in the static route. All decoded frames, copied packet
hashes/timing and complete decoding are checked. Results retain reports and clips.

Run `sudo bash /absolute/path/to/package/run.sh`. Wait for `Started`; after that
the test is detached and survives shell disconnection. It shares the assigned
NVIDIA GPU with existing workloads, with a four-core/six-GiB container limit.
Set MUXMENDER_GPU_REQUEST in the root environment to select a Docker GPU request
instead of the default `all` if needed. No host/root Docker access is granted to
the container. Only its unique output folder is writable.

The queue remains unchanged. Passing preservation is not an HDR perceptual quality
score and does not authorize replacement. Visually assess all three excerpts;
full-file validation remains required before publishing any full encode.
