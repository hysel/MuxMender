# Trusted-network dashboard and queue feedback

Dashboard login is removed, including when the old password environment setting
remains present. Anyone with network access can view paths/logs and submit jobs.
Use only on a trusted LAN; do not port-forward this app. Explicit allowed hosts,
same-origin POST checks, CSRF tokens, read-only sources and preview confirmation remain.

Queue pauses now show their reason and processed/waiting counts. Inspection-only
requests explicitly say they do not convert videos. Existing unsupported failures
remain in history with a clearer reason; new eligibility rejections are skipped
without triggering the repeated-failure pause. No automatic retry/resume occurs.
Result status updates preserve open details when the displayed set is unchanged.

Build and update the existing app image tag to `20260918-v9`:

```sh
sudo docker build -f /mnt/FR4G/Apps/muxmender/app-build-20260918-v9/deploy/truenas/Dockerfile.app -t muxmender-app:20260918-v9 /mnt/FR4G/Apps/muxmender/app-build-20260918-v9
```

Keep mounts, GPU, allowed hosts and ports unchanged. The old password variable can
be removed. After deployment, use Resume queue to continue pending inspections.
