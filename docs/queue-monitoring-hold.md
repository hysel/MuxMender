# Active queue monitoring instruction — 2026-09-19

- Check the TrueNAS queue every 15 minutes while this monitoring session is active.
- Investigate newly failed jobs and technical skip reasons; fix and test repo code.
- Do not create, build, publish or deploy another Docker version until the queue
  has no pending or running jobs. Hold the previously staged v31 package as well.
- Do not patch the running container, restart the app, or bypass its validation
  and repeated-failure pause merely to make the queue continue.
- Do not delete or manually replace source media. Existing app jobs retain their
  previously approved publication policy.
- A failed quality/size test can be a valid keep-original decision, not a defect.
- The read-only observer logs state changes on E:. It does not itself fix code;
  investigation and fixes are performed by the active agent session.

Initial state: v30, unpaused, 2 running, 61 pending. Historical failed/interrupted
records are retained separately from new failures so they are not repeatedly
reported as new incidents.

## Initial failure review

- MP4 case A: fractional MP4 timestamp quantization; pending
  demux-time-base fix reproduced and tested locally. Deployment held.
- Timing case D: historical false 120-second stall with advancing frame count
  and missing mux timestamps. Current code already recognizes advancing frames;
  regression tests cover both genuine stalls and this false-positive case.
- HDR skips: pending automatic PQ/HDR10+ preservation integration. Read-only
  checks of HDR case C and HDR series C confirm PQ 10-bit
  BT.2020 and progressive sample frames with mastering/content-light metadata.
  Admission to trials is not a claim that quality or savings will pass.
- 4:4:4 case B and HDR case D: recorded efficient/quality-size
  outcomes, not automatically classified as software failures.

Observer: `E:\MuxMender-TestOutputs\queue-monitor-20260919-live`.
First scheduled snapshot: 2026-09-19 23:25:34 UTC. Interval: 900 seconds.

## 23:40 UTC check

- v30 remains unpaused: 4 running, 56 pending, 16 total replaced.
- Library case G completed validated publication.
- HDR series C hit the known PQ/HDR admission limitation; pending
  integrated route remains held, with no container change.
- Savings case A failed because its reference PTS 0.135 became 0.125 in
  encoded output. HEVC trials had 10.24% and 11.85% sample reductions but could
  not reach quality evaluation after the timing failure.
- Tested the held demux-time-base fix on that generated excerpt with local
  HEVC/AMF: all 263 frames passed native validation, max timestamp delta 0,
  copied-track validation and full decode passed; source checksum unchanged.
  No VMAF/replacement approval is implied and NVIDIA still needs its retry after
  the release hold ends. Evidence is under
  `E:\MuxMender-TestOutputs\RedHood-timing-monitor-20260919\fixed-test`.

## Additional held fix

Automatic skip history now records an evaluation-policy identifier. Changed
search policy or codec/quality/savings settings invalidate old automatic
conclusions, including full-output size rejections. Explicit keep decisions and
successful publication history remain protected. Active claims win even if old
decision fields are present, preventing duplicate concurrent work. Legacy trial
records need matching policy evidence before they suppress a fresh evaluation.

Local regression suite after this change: 500 tests, no failures, 3 platform
skips. No archive, image, deployment or app restart was performed for this fix.

## 23:55 UTC check and held color-finalization fix

Queue paused automatically after repeated failures: 3 running, 56 pending.
Artwork case B produced 263 encoded frames, then an unnecessary unspecified-
color bitstream rewrite rejected packets (HEVC SEI / AV1 metadata parsing) and
left zero video frames. Full validation prevented replacement.

The actual NVIDIA HEVC intermediate was copied read-only to
`E:\MuxMender-TestOutputs\Animal-color-monitor-20260919\encoded.mkv`.
Its three unspecified color fields already match the source; local FFprobe
counted 263 frames and FFmpeg strict decoding exited successfully. The held
code now publishes an exclusive hard link to the generated intermediate when
those fields already match, avoiding a pointless bitstream rewrite. Normal
full validation and quality checks remain required. Required metadata rewrites
now use `-xerror` to stop on packet rejection. This is not a full-file quality
or replacement approval. No media source was changed.

Regression suite: 501 tests passed, 3 skipped. User direction requested before
resuming the paused v30 queue; no release, deployment or app restart performed.
