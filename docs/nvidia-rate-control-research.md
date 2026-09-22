# NVIDIA rate-control research

An encoder being available does not mean it can make every video smaller at the
requested quality. We test the installed GPU, driver and FFmpeg together, then
measure separate output copies. A working older card is not rejected simply
because it cannot encode AV1.

## What we found on the Pascal representative

In a 72-frame HDR diagnostic, CQ18 and CQ12 produced exactly the same output size
and quality score with the default settings. An explicit peak-rate ceiling made
CQ changes affect the result again. A lossless control matched all source-frame
pixel hashes, helping distinguish rate control from a damaged decode or alignment.

The shared automatic engine and CLI adapter accept `--nvenc-maxrate-mbps` for
HEVC/AV1 NVENC tests. This optional setting is a **maximum**, not a requested output
bitrate or a promise of savings. It is not enabled by default and there is no
P4000-specific encoding branch. The research value of 200 Mbps is not a recommended
setting for every GPU or source.

For a separate test copy, the shared CLI can be used as follows:

```sh
python3 python/media_workflow.py --help
```

Use the ordinary source/output and quality settings for that workflow, adding
`--nvenc-maxrate-mbps 200` only when investigating measured NVENC rate-control
behavior. Keep outputs separate and retain the originals. Quality, timing,
metadata, decoding and size checks still determine whether an output is usable.

The first full trial recheck still kept its HDR original: smaller candidates did
not meet the quality floor, and better-quality candidates did not meet the 10%
savings requirement. Fixing the rate-control response does not force conversion.
The second HDR excerpt also kept its original: compact saved 5.482%, below the
selected 10% minimum, and smaller adaptive outputs failed quality. Neither case
qualifies a publishable HDR output.

## Scope and next qualification

This work establishes a tested setting and a reproducible diagnostic, not automatic
deployment or certification of all older NVIDIA cards. Before making this an
automatic retry, compare both ordinary and explicit-ceiling settings across more
sources and the newer NVIDIA test host, including full-output validation. Keep
the selected rate setting in trial and final-encode evidence so they agree.

See [the qualification record](p4000-qualification-20260920.md) for outcomes and
test locations. `tools/research_nvenc_rate_control.py` runs the small diagnostic;
`tools/run_nvidia_generation_cases.py` runs separate copies through the shared
conversion and validation workflow. Diagnostic outputs are not publication-ready.
