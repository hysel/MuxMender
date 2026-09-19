# Resident MuxMender app (native TrueNAS GPU and storage settings)

Use **Apps > Discover Apps > Custom App**, not Install via YAML. The guided
installer already implements TrueNAS's native GPU selector and host-path mounts.
Plex's catalog questions reference `definitions/gpu_configuration`; these native
controls support non-NVIDIA passthrough and selection of detected NVIDIA cards.
A custom YAML app does not acquire a Plex-like edit form merely by adding a
questions.yaml file. No custom catalog registration or public image publication
has been performed here.

## Image

Build `deploy/truenas/Dockerfile.app` with the repository as its context, tagging
the image `muxmender-app:20260916-v2`. This adds Python inside the container image
only. Base FFmpeg/NVENC build remains pinned. No host driver/apt modifications.
Use this local image in the guided installer with pull policy **Never** where
available (do not request pulling this unpublished local tag from Docker Hub).
If the UI requires a remote image, stop and publish an image to a user-approved
registry as a separate authorized step; do not silently publish the repository.

## User and network

- Run as the chosen existing account. Here: UID/GID **3005/3005** (`muxmender`).
- Map TCP container port **8765** to an unused host port, e.g. **8767**.
- Dashboard is read-only, but reveals filenames/logs. Do not expose to the internet.
- HTTP Basic credentials are not encrypted by plain HTTP; use a trusted LAN or
  HTTPS reverse proxy. A non-loopback listener requires a >=12-character password
  and an explicit Host allowlist. Do not use another account's password.

Environment variables:

| Name | Value / meaning |
|---|---|
| MUXMENDER_DASHBOARD_PASSWORD | A new unique password, at least 12 characters |
| MUXMENDER_ALLOWED_HOSTS | `truenas:8767,192.168.1.232:8767` for this installation; change to actual URL host:port |
| MUXMENDER_MEDIA_ROOT | `/media` (container path, default) |
| MUXMENDER_OUTPUT_ROOT | `/output` (container path, default) |
| MUXMENDER_SOURCE | Optional path relative to `/media`; blank starts dashboard only |
| MUXMENDER_JOB_ID | Unique ID for each requested job; reused IDs never restart a conversion |
| MUXMENDER_PLAYBACK_CODECS | `hevc,av1` only after verifying those codecs on intended players |
| MUXMENDER_FULL_COPY | `false` (default trials only), or `true` for best eligible full safe copy |

Dashboard username is **muxmender**. Host allowlisting and authentication apply
to the page and every API/log endpoint. No dashboard endpoint starts jobs,
installs drivers, writes to media, or changes mounts. Settings are edited in TrueNAS.
Dashboard stays resident when a worker finishes. Interrupted jobs require a new
explicit job ID; no automatic restart/overwrite of existing output is performed.

## Storage (native host-path chooser)

1. Add a Host Path storage entry: choose the media dataset/folder, mount at `/media`,
   enable **Read Only**. Here the host source is `/mnt/FR4G/Media`.
2. Add a separate writable Host Path at `/output`. Here it is
   `/mnt/FR4G/Apps/muxmender/output`, owned by the app user.
3. Do not enable recursive ACL/ownership changes on media. Do not mount the Docker
   socket. The worker independently checks the source is within `/media`, the
   media filesystem is mounted read-only, and output is a separate directory.

Paths are deployment settings, not baked into the image. Extra media mounts can
be configured through TrueNAS, but this first workflow uses one selected media
root per job. Mounts cannot be created by changing a textbox inside the container.

## GPUs (native Resources settings)

- NVIDIA: choose the intended card(s) from TrueNAS's detected NVIDIA list.
  Do not supply a fixed UUID or set NVIDIA_VISIBLE_DEVICES=all in the image.
- Intel/AMD: enable **Passthrough available (non-NVIDIA) GPUs** as appropriate.
  Ensure the selected app user has device access using TrueNAS's device/group
  settings. Do not chmod host device nodes or grant privileged mode.
- Hardware vendor detection runs inside the app, using exposed DRM nodes and
  NVIDIA tools. Encoder initialization must still succeed before a trial runs.
- GPU passthrough is not a promise of encoder support: the existing AMD AMF flow
  is Windows-specific and Linux AMD VAAPI is not yet integrated into auto mode.
  Intel QSV and other cards need actual target-hardware validation. No automatic
  CPU fallback is made when the exposed GPU lacks a supported working encoder.

The app currently uses the first working encoder/device selected by FFmpeg within
the devices exposed by TrueNAS, serially; it does not balance work across GPUs.
For deterministic card selection, expose only the desired NVIDIA card in TrueNAS.

References:
- https://apps.truenas.com/managing-apps/installing-custom-apps/
- https://github.com/truenas/apps/blob/master/ix-dev/stable/plex/questions.yaml
