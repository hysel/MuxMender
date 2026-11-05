# Reading the dashboard

The dashboard should answer three questions: what is running, what is it doing,
and what happened to the files that finished?

Lifetime savings and compact server readings stay at the top of Overview.
The CPU, GPU and RAM values remain visible while the next reading arrives.
The last-update time tells you when they were collected. If refreshing fails,
a small message appears and the dashboard retries automatically; it does not
mean a conversion has stopped. Open **Resource details** for more information.

## Three places to work

A full safe copy keeps the original until you decide otherwise. In Results,
choose **Replace original with this copy** on an eligible validated result.
The confirmation shows both sizes and the destination. **Keep original**, the
close button and Escape dismiss it without replacing anything. Approval queues
verification and publication of that copy; it does not encode the video again.
The original is removed only after the shared replacement checks succeed.
Read-only media, changed/missing files or recovery journals prevent approval.

Resource-profile feedback appears beside **Apply resource profile**. **Saved**
means the setting was recorded, not that four workers have started. Faster still
waits for sustained headroom and respects GPU sharing. If a request times out,
check the saved setting before trying again; a lost response can follow a
successful save. These controls are additions after v59 and require an updated
app image.

- **Overview** shows the queue, current work and the step each video has reached.
- **Add videos** lets you choose a folder or one video, pick an action, then
  review the selection before adding it to the queue. Subfolders are included
  by default. Fine-tuning is optional; the action and confirmation remain yours.
- **Results** explains the latest outcome for each video. Quick filters show
  replacements, kept originals or items needing attention. Expand details for
  diagnostic evidence, previous attempts and retry options.

The selected results filter describes the list below, not the whole queue.
**Completed results** also keeps ongoing retries of previous outcomes visible;
use **Queued & running** to see active and waiting requests. A retry's current
state takes precedence over an old failure; previous outcomes remain in details.
Check **Overview** for whether the queue is running, paused or waiting.

**Freeze display only** stops live screen updates, not processing. Use the queue
pause control to stop new starts after current work finishes, or Cancel jobs to
request cancellation. Server-sharing Apply buttons sit beside their settings.

After cancellation, submitting a new folder or video starts processing
automatically; cancelled jobs stay cancelled. An intentional pause or a recovery
pause still needs Resume. Resource limits or other apps using the GPU can delay
the start. Keep-only requests do not restart processing.

Lifetime savings and CPU, GPU encoding use and available RAM remain above all
three views. Missing measurements say unavailable, not zero. Resource details,
server-sharing settings and report exports are there when you need them, without
competing with current progress. Use **Manage displayed results** to hide finished
results; it does not erase processing history or delete media.

Light, dark and system appearance are available. Controls have visible keyboard
focus, labels and touch-sized targets. The cancellation dialog can be dismissed
with its close button, Go back, Escape or a click outside. An empty queue shows
a message instead of opening a confirmation. Closing it does not cancel work.

The design preview uses illustrative data and cannot operate on media. It is not
the production dashboard or evidence of a completed conversion.

## Follow the current step

Automatic jobs report these steps when they apply:

1. Inspect the source.
2. Compare short test encodes.
3. Encode the full video.
4. Validate the result.
5. Put the approved replacement in place.
6. Clean up eligible work files.

Safe-copy jobs do not replace the original or run replacement cleanup.

A percentage belongs to the current check. Reaching 100% on that check does not
mean the whole job is finished. The time estimate also covers that check, not
every remaining step. When there is not enough information yet, the dashboard
shows a measuring or waiting message instead of inventing a percentage.

## Read the result

A completed conversion passed its applicable checks. A kept file may simply
have missed the quality or size target. A failure means something prevented
the work from completing; read its reason before retrying.

Older job records may not have the newer step information. The dashboard labels
that gap rather than guessing. Technical details and resource settings can be
expanded when you need them.

## Understand the savings

Size reduction compares the original with the output. Lifetime savings count
confirmed replacements, not every test copy. Percentages and GB describe file
sizes; snapshots may mean your storage pool does not immediately show the same
amount of free space.

Check the [release notes](https://github.com/hysel/MuxMender/releases) for the
features available in your installed version.

## GPU activity readings

The next dashboard update shows **GPU Encoding**, **GPU Decoding** and **GPU
Compute** separately beside CPU and available RAM. Encoding and decoding use
dedicated video engines; low compute usage does not mean encoding is idle.

These readings include other apps. With multiple visible GPUs, each value is
the highest reading for that engine, possibly from different cards. Do not add
the percentages together or interpret them as MuxMender-only usage. Missing
readings show **Unavailable**, and stale snapshots show **Stale** rather than
presenting an old number as current. This display does not change throttling.

## Find copies you can use to replace originals

Choose **Ready to replace** in Results, or in its Show dropdown. This shows
the latest results that offer **Replace original with this copy**. Search and
folder filters still apply. Opening the action checks that the source and copy
are still available; you must confirm before a replacement is queued.

## Automatic resource use

**Automatic** starts with one video. It checks available CPU and RAM, GPU engine
activity, storage pressure and the stages already waiting before starting another.
The app may keep one video active when its checks can use the available capacity.
It can also overlap an encode with another video's checks when those stages fit.

Quiet, Shared and Faster set upper limits. Choosing Faster does not ask the app
to keep four videos running. Existing saved profile choices are kept after an
upgrade; new installations start with Automatic.

The resource status explains whether the app is focusing on current work, trying
an overlap or waiting for headroom. An overlap trial is not a measured speed gain.
Per-stage thread counts stay within the tested limits. Container CPU and memory
limits still apply, and another application's activity can delay new work.
When capacity falls, running work drains before more work starts. GPU sharing
can pause supported stages separately when another app needs the GPU.

Resource scheduling does not change the selected quality profile, preservation
checks or savings target. More active videos is useful only if the batch finishes
sooner; it is not a goal by itself.

## File-size estimates

New results compare two sample estimates: one based on compression ratios, and
one based on actual output rates. The larger estimate is shown so the new method
does not promise more savings than the older one. Their range describes the
tested scenes and estimates; it does not guarantee the size of unseen content. Files with covers or
attachments keep the older sample-only estimate until those fixed sizes can be
accounted for separately. The finished file still has to pass the real savings
and quality checks before replacement.

Small HDR reference clips can reuse a lossless rendered copy within the same job.
Every rendered frame is checked against that copy before it is used, and its
checksum is checked again on reuse. This changes only the picture-comparison
work, not the delivered video. Cache space is bounded and joins normal task
cleanup. Long videos and ineligible clips keep the ordinary comparison path.
