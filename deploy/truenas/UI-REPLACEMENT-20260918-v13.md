# UI-controlled replacement

Replaces v11/v12 configuration instructions. Copy vs replacement is selected and
confirmed per request in the UI. No replacement environment switch is required.
Read-only media permits copies but rejects replacement; writable media permits both.
All validation, preview confirmation and publication safeguards remain unchanged.

Required user-configured environment variables for the existing app:

```text
MUXMENDER_ALLOWED_HOSTS=truenas:8767,192.168.1.232:8767
MUXMENDER_CONTROLS_ENABLED=true
MUXMENDER_PLAYBACK_CODECS=hevc,av1
```

The host list is a request validation allowlist, not authentication. Keep network
access restricted to trusted users. Playback codecs are the verified player choices.
Do not remove image-provided NVIDIA_DRIVER_CAPABILITIES or runtime-assigned GPU vars.

Keep host media mounted at /media (read/write for replacement), output at /output,
container port 8765 mapped to 8767, app identity and GPU assignments unchanged.
Remove obsolete user-configured MUXMENDER_REPLACEMENT_ENABLED,
MUXMENDER_REPLACEMENT_ROOT, MUXMENDER_DASHBOARD_PASSWORD, MUXMENDER_SOURCE,
MUXMENDER_JOB_ID, MUXMENDER_FULL_COPY, MUXMENDER_ADAPTIVE, MUXMENDER_QUEUE_ENABLED.
MEDIA_ROOT, OUTPUT_ROOT, BIND and PORT are unnecessary when using these default paths
and container port. They remain supported for custom installations.

```sh
sudo docker build -f /mnt/FR4G/Apps/muxmender/app-build-20260918-v13/deploy/truenas/Dockerfile.app -t muxmender-app:20260918-v13 /mnt/FR4G/Apps/muxmender/app-build-20260918-v13
```

After active jobs finish, change the existing app tag to 20260918-v13.
