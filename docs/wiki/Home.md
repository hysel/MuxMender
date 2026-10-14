# MuxMender user guide

MuxMender helps you make an existing video library smaller. Choose your videos,
tell it what matters to you, and let it try a smaller version. If that version
doesn't pass the checks, it keeps the original and tells you why.

It works with videos you've already ripped or obtained legally. It doesn't
download videos, bypass copy protection, or help distribute unauthorized copies.

## Start here

Install the ready-built image **`ghcr.io/hysel/muxmender:stable`** from GitHub
Container Registry. There is no local image build or conversion script to run.
After installation, use the browser interface for all video processing.
Follow the installation guide and start with a small safe-copy run.

- [Set up the app](Installation.md)
- [Run your first conversion](First-conversion.md)
- [Choose quality and size settings](Settings.md)
- [Manage the queue](Queue.md)
- [Understand results and disk savings](Results.md)
- [Solve common problems](Troubleshooting.md)

For your first run, choose a few videos and **Create smaller copies**. That lets
you check the results while keeping your originals. When you're comfortable,
you can choose replacement instead.

Replacement permanently removes the original after the new file passes its
checks and is verified at its destination. Keep a backup of anything you can't
replace.

## What the app does—and doesn't promise

Automatic encoding compares the options available on your GPU. It doesn't
convert everything just because you selected a folder: some videos are already
compact, some won't meet your quality target, and some need attention.

The app checks picture quality, timing and the information carried by the file.
That doesn't promise identical pictures or playback on every device. Your
player still needs to support the output's video, audio and subtitle formats.

This guide describes the current code. An older installed image may have
different labels or fewer controls. Updating the repository doesn't update your
running app.
