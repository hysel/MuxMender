# Mixed-folder replacement

Replacement preview accepts mixed supported containers, including MKV, MP4 and AVI.
Encoding eligibility checks still apply to each file: container support is not a
promise that every video codec, bit depth or color profile can be processed.

Validated output is MKV. MKV sources keep their filename; other sources retain their
stem with a .mkv extension. Adjacent sidecars are not modified. If a destination name
exists (including case-only differences), that job is skipped without pausing the
folder queue. Publication uses exclusive hard-link creation for new names, so a
late collision cannot overwrite an unrelated file. Recovery artifacts remain after
interrupted/failed publication. Originals are removed only after final verification.

No mount/environment changes from v13. Build and set image tag 20260918-v14 after
active jobs finish:

```sh
sudo docker build -f /mnt/FR4G/Apps/muxmender/app-build-20260918-v14/deploy/truenas/Dockerfile.app -t muxmender-app:20260918-v14 /mnt/FR4G/Apps/muxmender/app-build-20260918-v14
```
