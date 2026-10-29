# Solve common problems

## The dashboard won't open

Check that the app is running and use the published **host port**. If host 8767
maps to container 8765, open `http://YOUR-SERVER:8767/`, not port 8765. The
TrueNAS portal link must use that same host port.

If the app reports a missing path, check the host folders in its mount settings.
Both must exist. Inside the container, the app expects `/media` and `/output`.
Check any extra mounts too. An old optional GPU-monitor path can prevent saving
the app if that host path no longer exists. It is not required for basic conversion;
follow the current GPU-sharing setup if you want that feature.

## TrueNAS doesn't show an update

Use repository `ghcr.io/hysel/muxmender` with tag `stable`, and enable image update
checks and downloads. A numbered tag does not follow the stable channel.
Checks are periodic, so an update may not appear immediately.

A successful GitHub build, merged change or draft release is not a published
stable update. Wait for publication rather than building it yourself. See
[update guidance](https://github.com/hysel/MuxMender/blob/main/docs/stable-updates.md).
The release test tools are for maintainers, not something you need to install.

Faster image packaging does not mean faster video processing. Release notes
describe changes that affect conversion speed separately.

## I see permission denied

Check permissions for the user the app actually runs as. It needs read access
to media and write access to output. Replacement additionally needs write access
to media. Don't solve this by granting everyone full access to the whole pool.

## Videos are waiting, but nothing starts

Read the queue's waiting reason. It may be deliberately paused, waiting for
storage or memory headroom, sharing the GPU, or recovering interrupted work.
Resume doesn't override those conditions.

An idle GPU isn't proof that nothing is happening. Inspection, track copying,
some validation and storage work can run without the encoder being busy.

## A conversion takes a long time

Look at the current step first. Full encoding and validation both read substantial
amounts of data. GPU encoding doesn't make every other step GPU-accelerated.
More concurrent jobs can make each job slower on a shared GPU or storage pool.

In the next release, CPU-only validation can run alongside busy GPU encoding
when CPU, RAM and storage have sustained headroom. GPU work keeps its separate
limits. This can reduce unnecessary waiting; it does not guarantee a particular
speed increase or change the checks applied to a video.

GPU inspection depends on the source codec as well as a matching qualification.
A verified HEVC or AV1 reader does not automatically accelerate H.264 inspection.
The current-step details identify the selected reader; GPU encoding can still
be used later even when inspection needs the CPU.

Keep enough temporary disk space, check resource pressure and choose a time limit
appropriate for your files. Lower-resolution copies may be faster or smaller,
but deliberately change the picture; they aren't a free quality-preserving shortcut.

## The original was kept

Open its reason. If no candidate meets your quality and savings choices, keeping
the original is the expected result. You can deliberately change those choices
for a new request. The app won't do that for you just to show a successful conversion.

If the reason is a decoding or preservation error, retrying unchanged settings
may reproduce it. Include the app version, action, current step and sanitized
error text when reporting a problem. Don't publish private file paths or video names.

An existing audio decoding warning may allow conversion when the compressed
audio and timing can be preserved exactly. See [audio warnings](Results.md#warnings-about-original-audio).

## Cancel was clicked, but the video still appears

Cancelled attempts remain in history. Check its current state rather than the
presence of a result card. Active workers may need time to stop, and an in-progress
replacement finishes safely. Avoid restarting repeatedly while cancellation is settling.

## Free space hasn't increased

Check whether you created a copy or actually replaced the original. Then check
retained copies, unresolved work and storage snapshots. Don't delete the entire
output folder: it contains the records the app uses to avoid repeating work and
recover interrupted replacements.

Old release downloads and development test files are separate from your library.
They can be reviewed after an update is working, but keep a known-good rollback
image. Avoid broad Docker cleanup commands on a server that runs other apps.

## Different duration reports

A duration warning can also come from how containers describe time: one may
report elapsed length while another reports the ending position. The next
release can verify exact video clock conversion after a full frame audit,
while keeping copied audio and subtitle checks unchanged. Retry an affected
failure after updating; you do not need to change the source yourself.

## Conflicting video timestamps

If a result says the source has conflicting video timestamps, some pictures
share a playback time or are scheduled out of order. MuxMender keeps
the original because conversion would require changing that timing. This is
different from a variable frame rate, which is supported.

A short check near the end can catch these conflicts before a full encode.
Files that pass that check still need complete validation; it does not inspect
the whole timeline.

Retrying the same file will not repair its timestamps. Use a source copy with
correct timing. MuxMender does not silently rebuild the timeline or shift the
video against its audio.
