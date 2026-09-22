# MuxMender

Make more room in your video library.

MuxMender re-encodes **previously ripped or otherwise lawfully obtained videos**
into smaller files. It tries suitable settings, checks the result, and keeps the
original when the tested options do not meet your quality and space-saving targets.

It works with files you already have. It does not find, download or share videos.

[Get started](docs/GETTING-STARTED.md) · [Project status](docs/STATUS.md) · [Roadmap](docs/TODO.md)

## How it works

1. Choose a video or folder. Subfolders are included by default.
2. Choose what to do: inspect, test a short clip, make a converted copy, or replace
   the original after successful checks.
3. Set your quality and savings targets, or use automatic encoding selection.
4. Follow the current step and read the result: converted, kept, or needs attention.

The app compares supported HEVC/H.265 and AV1 options. It preserves the original
resolution by default and checks audio, subtitles, chapters and HDR information
where supported. Not every video will get smaller, and lossy encoding cannot
promise an identical picture.

## You decide what happens to the original

**Safe-copy mode keeps it. Replacement mode permanently removes it only after
the new file passes validation and is verified in its destination.**

Choose safe-copy mode if you are unsure. Converted copies take extra space until
you remove or replace the original. Lifetime savings count confirmed replacements;
snapshots and retained work files can still occupy disk space.

The app uses a separate output folder for work in progress and job records.
After verified replacement, eligible generated files can be
[cleaned automatically](docs/replacement-cleanup.md). Active work and safe-copy
outputs are not swept away.

## Start with a small test

The [getting-started guide](docs/GETTING-STARTED.md) walks through the app.
You can also inspect one file from a terminal without converting it:

```powershell
python python/media_workflow.py "D:\Media\Example.mkv" --output-dir "E:\Optimized"
```

Run from the repository folder with Python 3.10 or newer, FFmpeg and FFprobe.
Available encoders depend on your FFmpeg build and hardware. To see the options:

```powershell
python python/media_workflow.py --help
```

The app and standalone automatic workflow share processing services. Older
[standalone commands](docs/STANDALONE.md) and the [local planner](docs/WEBUI.md)
have their own documented controls and defaults.

## What has been tested?

Selected SDR, HDR10, legacy AVI and DVD-rip workflows have passed project tests.
Results depend on the input, GPU, driver, encoder and player—not just the file
extension. See [tested formats](docs/TESTED-FORMATS.md) for the scope and limits.

Dolby Vision and combined Dolby Vision/HDR10+ research has promising results,
but those automatic routes remain disabled until integration is qualified.
A successful experiment does not mean every similar file is supported.

The [status report](docs/STATUS.md) separates merged code, recorded tests and
deployment. Merging code does not update a running TrueNAS app.

## Responsible use

**We do not support piracy.** Only process media you have the rights or permission
to use. Do not use MuxMender to obtain or share unauthorized copies. This project
is for optimizing an existing library, not downloading content or bypassing DRM.

## For contributors

- `python/`: shared processing code and commands.
- `python/ui/`: dashboard and queue interface.
- `tests/`: automated regression tests.
- `docs/`: guides, roadmap and technical evidence.
- `deploy/`: packaging and deployment files.

From the repository root, run the suite with:

```powershell
python -m unittest discover -s tests
```

Use neutral example names in code, docs and commit messages. Never include real
media titles or private library paths. Keep technical evidence in the research
notes, while making everyday guides understandable without reading the code.
