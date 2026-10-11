# Manage the queue

**Overview** shows waiting videos, active work and the current processing step.
You can add another folder while existing work continues.

## Pause, resume and cancel

- **Pause new starts:** let active work finish, but don't start another video.
- **Resume queue:** allow waiting work to start when resources are available.
- **Cancel jobs:** request that active work stop and cancel waiting requests.
  A replacement already being committed finishes safely.
- **Remove a waiting item:** take that request out of the queue without deleting
  the source video.

Cancellation isn't always instant. The app needs to stop its workers and leave
files in a recoverable state. Closing the browser doesn't cancel processing.
Freezing the display stops screen updates only.

Adding work after an empty or cancelled queue normally starts it automatically.
An intentional pause or recovery pause still needs Resume. Waiting for resources
is different from being paused.

## Share the server

The resource profile controls how much parallel work the app may admit. A faster
profile allows more workers when there is sustained headroom; it doesn't promise
that four videos will always run or impose a hard resource limit.

**Yield GPU to other apps** requires host GPU monitoring. It can temporarily
pause supported media stages when competing work appears, then resume after a
quiet period. Paused work can still hold GPU memory. If monitoring is unavailable,
the app may wait before starting more work.

Check the explanation beside the queue before changing settings. Low storage
headroom, memory pressure or GPU sharing can delay starts even with an empty GPU
utilization graph.

## Try a folder again

MuxMender remembers processing decisions so repeated scans don't automatically
repeat all the work. Relevant changes to the source or settings can make another
attempt useful. Use the retry and preview controls to see what will be queued.
Don't delete the output folder just to hide old results: it also holds history
and recovery information.
