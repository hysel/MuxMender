# TrueNAS NVIDIA bootstrap

Prepared for TrueNAS 25.10.7, muxmender UID/GID 3005, and the discovered RTX 5050 UUID.
This is a one-shot FFmpeg preflight, not the full MuxMender service. No Python,
dashboard, media scan, or media conversion is launched. Four sequential checks
test HEVC/AV1 encoder initialization with 8/10-bit generated frames.

## Install

1. In an administrator shell, create ONLY the new output directory:

   ```sh
   sudo install -d -o 3005 -g 3005 -m 0750 /mnt/FR4G/Apps/muxmender
   sudo install -d -o 3005 -g 3005 -m 0750 /mnt/FR4G/Apps/muxmender/output
   ```

2. Apps > Discover Apps > three-dot menu > Install via YAML. Use app name
   `muxmender-preflight` and paste `nvidia-preflight.yaml`.
3. Installation downloads the LinuxServer FFmpeg image. No host packages or
   drivers are changed. Existing TrueNAS NVIDIA runtime support is required;
   do not install the toolkit with host apt if startup fails.
4. Watch the app logs. A successful run prints four PASS lines and exits 0.
   An exited/stopped app after completion is intentional; restart is disabled.
   A failed startup is NOT a passed encoder test.
5. Results persist in `/mnt/FR4G/Apps/muxmender/output/preflight-*` and are
   readable by the dedicated SSH account without granting Docker access.

The app has no network, published ports, Docker socket, privileged mode, or
write access to `/media`. It runs as UID 3005 with a read-only root filesystem.
Each run creates a unique directory. No cleanup/deletion is performed.
The SSH account's existing host media permissions are not changed by this app.

The initial `latest` image failed all four checks: it required NVENC API 13.1
while driver 580.173.02 exposed API 13.0. Do not upgrade the TrueNAS host driver
to satisfy that image. The configuration now pins LinuxServer `8.0.1-cli-ls61`
to its linux/amd64 manifest digest. Its build uses nv-codec-headers n13.0.19.0,
whose documented Linux driver minimum is 570. The publisher registry manifest
was checked. Runtime validation of this replacement is still pending.

To retry, edit the existing custom app YAML, replace its image with the new
image line from `nvidia-preflight.yaml`, and save/start the app. Existing logs
are preserved; a fresh result directory will be created. No permission or
driver changes are needed. A completed successful one-shot app may show stopped.

## Next gate

After preflight success, package the Python CLI with a pinned FFmpeg image and
test a short media COPY. Keep sources read-only and outputs separate. Validate
resolution, aspect ratio, audio/subtitles, color metadata and playback before
starting a library batch. No source replacement is authorized by this setup.

## Measured full-copy pilot (prepared, not yet deployed)

`auto-pilot.yaml` builds an isolated image from the pinned FFmpeg base and adds
Python INSIDE that image. The staged context is
`/mnt/FR4G/Apps/muxmender/auto-build-20260915-v1`. No Docker/administrator rights
were granted to the SSH account. The archive copy hash and Linux CLI import were
checked; the YAML parsed and its safety mounts were checked. Image build/runtime
validation requires deploying through the TrueNAS administrator UI.

Install as a separate custom app named `muxmender-auto-pilot`, using the full
contents of `auto-pilot.yaml`. Do not run the prior comparison app concurrently.
The configured source is the previously tested Series A extended file
(about 2 hours 18 minutes, not a single 45-minute episode). It creates three short
references and tests both codecs at balanced/compact settings, then encodes a full
copy only if the quality, integrity and savings gates pass. No originals are
replaced. Source remains mounted read-only; outputs stay under `/output`.

The build needs network access to download Python packages; the running app has
no network access. No host apt packages, drivers, Plex settings or media ownership
are changed. A stopped app after successful completion is intentional. Image
construction and the integrated NVIDIA run are not yet certified by local tests.

References:
- https://apps.truenas.com/managing-apps/installing-custom-apps/
- https://github.com/linuxserver/docker-ffmpeg
- https://github.com/linuxserver/docker-ffmpeg/blob/8.0.1-cli-ls61/Dockerfile
- https://github.com/FFmpeg/nv-codec-headers/blob/n13.0.19.0/README
