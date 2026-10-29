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

HDR inspection reads every frame, including its timing and color metadata. It
can take longer than encoding when it needs the CPU reader. The current step
shows which reader is in use.

GPU frame inspection requires checks for the exact reader build, GPU, driver
and video format. The app performs these checks automatically, using the complete
CPU reference from the first matching video and generated damaged-input controls.
It saves successful results in the output storage and reuses them for later jobs.
No administrator script or special host mount is needed.

The first check adds a full GPU comparison to the normal CPU inspection. If an
update changes the reader or compatibility rules, or the GPU or driver changes,
the app checks again. Until it has a matching result with a measured speed benefit,
it retains complete CPU inspection. GPU encoding can still work normally.

Raising the time limit gives a slow check more time; it does not make the check
faster. Lowering quality settings does not speed up this metadata check either.
The app never skips frames or drops preservation checks to meet a deadline.
