# TrueNAS v32 — accumulated queue fixes

Version: `20260920-v32`. Supersedes the held v31 build context.
The user lifted the release hold on September 20. Staging does not deploy or
resume the queue and does not alter source media.

Includes the automatic PQ/HLG/HDR10+ preservation route, demux-time-base MP4
timing fix, adaptive NVENC quality search, guarded HDR subprocesses and streaming
exit-status fix described in v31. HDR quality is a common-render VMAF proxy,
not a percentage of visual fidelity or native-HDR quality certification.

Additional fixes:

- Avoid rewriting already-correct unspecified color metadata. Artwork case B
  had 263 valid NVIDIA-encoded frames; an unnecessary metadata filter rejected
  the packets. Matching streams now use an exclusive hard link to the generated
  intermediate and still undergo full validation. Necessary rewrites use
  `-xerror` so packet rejection cannot masquerade as successful processing.
- Automatic skip history records an evaluation-policy identifier. Changed
  search policy/settings allow re-evaluation; active jobs, completed replacements
  and explicit keep decisions remain protected. Legacy records need matching
  evidence before suppressing a new evaluation.
- Added a read-only, secret-filtered queue observer and regression coverage.

Verification: 501 local regression tests, 3 platform skips before packaging.
The actual Artwork case B HEVC intermediate passed strict decoding and frame
counting. Savings case A's 263-frame excerpt passed timing and preservation
with the demux-time-base fix on AMD. Neither is full-file NVIDIA qualification.

Remaining work: retry affected full files on the RTX 5050; investigate older
quality self-check, language metadata, timeout and input-admission failures.
This release does not claim all historical failures resolved. Source resolution,
quality thresholds, track preservation and verified-publication requirements
remain enforced. No silent CPU fallback or automatic queue resume is added.

Build the staged context:

```bash
sudo docker build -f /mnt/FR4G/Apps/muxmender/app-build-20260920-v32/deploy/truenas/Dockerfile.app -t muxmender-app:20260920-v32 /mnt/FR4G/Apps/muxmender/app-build-20260920-v32
```

Then select `muxmender-app:20260920-v32` in the existing TrueNAS app. Preserve
mounts/settings. Confirm version and queue state before resuming pending work.
