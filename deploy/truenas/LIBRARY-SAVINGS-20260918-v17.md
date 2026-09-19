# Whole-folder queue and lifetime savings

Removed the 100-video preview/pending-job caps and the 1,000/5,000-item folder
listing caps. Browsing still uses pages of 100; this is pagination, not a request
limit. The UI shows discovery counts while loading pages. All pending/running
requests remain visible, plus the latest 100 finished requests. Persistent history
and source/free-space/validation safeguards remain in effect. Very large trees
still require traversal, memory and JSON storage; this is not an infinite-resource
guarantee or an asynchronous indexed library scanner.

The top savings card shows recorded confirmed replacements in decimal GB/TB,
replacement count and weighted overall reduction. Safe copies, failures and
estimated savings do not count. Retained manual approved-replacement receipts
are included and deduplicated against their originating UI request. Records must
be retained on persistent output storage. Older unrecorded operations cannot be
reconstructed reliably. Output copies/snapshots may still consume pool capacity.

Concurrency remains one file at a time. A future worker pool must isolate job
tracking (currently process-global), track/cancel multiple children, reserve disk
and GPU resources, and exclusively claim source/destination paths before work.
Do not simply call the existing worker from multiple threads.

After active work finishes:

```sh
sudo docker build -f /mnt/FR4G/Apps/muxmender/app-build-20260918-v17/deploy/truenas/Dockerfile.app -t muxmender-app:20260918-v17 /mnt/FR4G/Apps/muxmender/app-build-20260918-v17
```

Set image tag to `20260918-v17`; no mount/environment changes are needed.
