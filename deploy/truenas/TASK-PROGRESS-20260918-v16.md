# Task visibility

The measured conversion workflow now reports frame-inspection progress using
media timestamps, packet-inspection evidence growth, byte-based checksum and
publication-copy progress, and named metadata/comparison/storage-flush stages.
Frame percentage is an estimate of timeline coverage, not validation success.
Sparse subtitle tracks show inspected timestamps/evidence rather than a misleading
percentage. Evidence remains streamed to disk with bounded tail reads.

Every tracked task has a five-second heartbeat. The workspace displays heartbeat
age and stage elapsed time; after 30 seconds without an update it warns that status
is overdue. A heartbeat explicitly does not prove forward progress. Unmeasurable
steps do not invent a percentage or ETA. Existing encoder progress remains intact.
Publication now has its own tracked job, including post-copy checksum verification.

Probe failures, timeouts and guard failures cannot report successful completion.
Only the owned probe process is killed on failure. Quality gates and source
replacement conditions are unchanged. No media operations run during deployment.

Deploy after current work completes: running processes do not acquire new code.

```sh
sudo docker build -f /mnt/FR4G/Apps/muxmender/app-build-20260918-v16/deploy/truenas/Dockerfile.app -t muxmender-app:20260918-v16 /mnt/FR4G/Apps/muxmender/app-build-20260918-v16
```

Set app image tag to `20260918-v16`. Mounts and environment settings are unchanged.
