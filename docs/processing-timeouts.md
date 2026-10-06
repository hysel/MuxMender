# Processing time limits

In **Add videos → Encoding options**, set **Processing time limit per stage
(minutes)** before reviewing and queuing your selection. Choose 1–1440 minutes;
the default is 120. For example, 360 gives each long processing stage six hours.

This budget covers the shared automatic workflow's long encoding and validation
operations. It is not a deadline for the entire video: a job has several stages.
Waiting for the shared validation slot does not consume this budget. Short tool
availability checks, metadata probes, and stalled-encoder protection retain their
separate safety limits; this control does not disable cancellation or safety checks.

The selection is saved with each new job and shown in the request preview. It
does not change running or already queued jobs. Older jobs without a saved value
retain the previous 120-minute budget. To retry a processing timeout, select
**Retry skipped/failed files only**, increase the limit, and submit a new request.
Successful conversions are not invalidated just because you change the time limit.

The standalone workflow uses the same setting:

```powershell
python python/media_workflow.py "D:\Media\Example.mkv" --output-dir "E:\Optimized" --mode encode --playback-verified-codecs hevc --timeout-minutes 360
```

A timeout is not a quality verdict. The incomplete result cannot authorize
replacement. Reader timeout messages identify the stage, selected limit and last
measured inspection progress, so you can distinguish this from a rejected encode.

## HDR inspection performance

The automatic HDR reader and preservation finalizer now share the same bounded
CPU-thread selection. Compact JSON keeps every frame field and HDR side-data
value, including repeated keys, while reducing evidence-file I/O and storage.
Neither change skips frames or relaxes quality and preservation checks.

A bounded 120-frame UHD HDR source comparison measured roughly 5.9 seconds with
both two and four slice threads. Compact JSON reduced evidence bytes by about
35% with identical parsed frame data; it did not materially speed up decoding.
Frame threading measured about 2.1 seconds on that sample, but remains research
only because earlier tests found intermittent HDR metadata loss. This short
result is not full-file qualification or a promise of a 2.8× job speedup.

A follow-up compared six longer sections (720 decoded frames each) at early,
middle and late positions in two UHD HDR sources. All 4,320 frame records matched
exactly, including repeated HDR metadata keys. Slice/frame elapsed seconds were
38.0/12.0, 36.0/12.0, 38.0/14.0, 20.0/14.0, 18.0/14.0 and 18.0/12.0. These are
bounded section measurements on a shared host, not whole-file timings. Source
size and modification timestamps were unchanged; no media outputs were created.

The faster mode remains excluded from v45: matching these sections does not
resolve the previously observed intermittent metadata loss or prove preservation
across an entire file. Remaining qualification must include that regression and
complete-file metadata/timing comparisons before changing the production reader.
