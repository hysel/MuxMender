# MuxMender

Make more room in your video library.

MuxMender re-encodes **previously ripped or otherwise lawfully obtained videos**
into smaller files. It tries suitable settings, checks the result, and keeps the
original when the tested options do not meet your quality and space-saving targets.

It works with files you already have. It does not find, download or share videos.

[User guide](https://github.com/hysel/MuxMender/wiki) · [Get started](docs/GETTING-STARTED.md) · [Releases](https://github.com/hysel/MuxMender/releases) · [Report a problem](https://github.com/hysel/MuxMender/issues)

## Installation and availability

MuxMender ships as a Linux amd64 Docker image, not a TrueNAS-only app. It can
be hosted on Linux, TrueNAS, or Windows through Docker Desktop's WSL 2 Linux-container
backend. The current release targets NVIDIA GPUs and needs working GPU access
inside the container. MuxMender does not install or change host drivers; AMD and
Intel app qualification are deferred for now.

Our end-to-end release tests run on Linux/TrueNAS. Windows Docker Desktop is a
deployment option, but its encoding, replacement and host GPU-sharing behavior
have not yet been qualified by this project. Docker compatibility alone does not
guarantee that every GPU feature works on every host.

The [public wiki](https://github.com/hysel/MuxMender/wiki) explains the everyday
workflow. Install **`ghcr.io/hysel/muxmender:stable`** to follow the stable release channel.
GitHub Container Registry supplies the ready-built app. You do not need to clone
the repository, build an image on TrueNAS, or run conversion scripts. Once the
container is installed, select videos, set options and manage jobs in the browser.
Release testing is handled separately by maintainers. You do not need research
containers, qualification scripts or administrator helper commands to use the app.
GPU inspection checks also run inside the app. The first matching video may
need a complete CPU/GPU comparison; later jobs reuse the saved result when the
reader, GPU and driver still match. Keep the output storage persistent to retain
these checks and job history across updates. No separate qualification mount or
administrator script is needed.

See the [release notes and known limits](https://github.com/hysel/MuxMender/releases)
and [installation guide](docs/wiki/Installation.md). Start with a small folder
and safe-copy mode; publishing a new image does not update your installed app.

Releases include third-party notices and matching source/build
materials alongside the image. Those archives are for transparency and rebuilding;
they do not need to live in your media library or conversion output folder.

### Install on TrueNAS

Use a TrueNAS release with Docker-based Apps. You do not need to clone this
repository or build an image yourself.

1. Create a separate output dataset or folder, alongside—not inside—your media
   folder. It holds converted copies, temporary work and your job history.
2. In **Apps**, choose **Discover Apps → Custom App**. Labels can differ between
   TrueNAS versions. Name the app `muxmender`.
3. Enter repository **`ghcr.io/hysel/muxmender`** and tag **`stable`**.
   Enable image update checks in TrueNAS and do not use the **Never** pull policy.
   This lets TrueNAS check for stable image updates; it does not deploy them
   automatically. Numbered release tags are available for pinning or rollback.
4. Map host TCP port **8767** to container port **8765**. If you add a portal
   link, use HTTP and the **host port, 8767**, not 8765.
5. Add these host-path storage mounts. Create both host paths before saving:

   | Your server folder | Container path | Access for your first run |
   | --- | --- | --- |
   | Existing media folder | `/media` | Read-only |
   | Separate output folder | `/output` | Read and write |

6. Set the container user and group to an account with read access to your media
   and write access to the output folder. The image defaults to **UID 568, GID
   568**; you can use different numeric IDs that match your dataset permissions.
   Grant access through TrueNAS dataset permissions rather than recursively
   changing ownership of your whole library.
7. Add these environment variables:

   | Variable | Value |
   | --- | --- |
   | `MUXMENDER_CONTROLS_ENABLED` | `true` |
   | `MUXMENDER_ALLOWED_HOSTS` | `YOUR-SERVER:8767` |
   | `MUXMENDER_PLAYBACK_CODECS` | `hevc,av1` |

   Replace `YOUR-SERVER` with the hostname or IP you will open in your browser.
   To allow both, use comma-separated entries, for example
   `media-server:8767,192.168.1.50:8767`. Do not include `http://` or a trailing
   slash. List only playback codecs your players support; use `hevc` alone if
   you have not tested AV1 playback.
8. Assign your NVIDIA GPU using the app's GPU selector. The host needs a working
   NVIDIA driver. Do not enable privileged mode or mount the Docker socket.
9. Save, wait for the app to start, then open **`http://YOUR-SERVER:8767/`**.
   Choose a small folder and **Create smaller copies** for your first test.

If you prefer **Install via YAML**, use
[the release Compose template](deploy/truenas/compose.release.yaml), replacing
every `REPLACE_*` value, including the GPU UUID. See the official
[TrueNAS custom-app guide](https://apps.truenas.com/managing-apps/installing-custom-apps/)
for the platform's installation screens.

### Install with standalone Docker

On Linux, use Docker Engine, the Docker Compose plugin, a working NVIDIA driver
and the NVIDIA Container Toolkit configured for Docker. Confirm GPU access using
[Docker's GPU setup guide](https://docs.docker.com/engine/containers/gpu/).

On Windows, use Docker Desktop with the **WSL 2 backend and Linux containers**,
plus a compatible NVIDIA Windows driver. Follow
[Docker's Windows GPU setup guide](https://docs.docker.com/desktop/features/gpu/).
Windows-container mode cannot run this Linux image. Start with safe copies and
verify GPU encoding and playback before relying on replacement.

Installing FFmpeg or Python on the host is not required on either platform.

Create a `compose.yaml` file with the following contents. Replace the two host
paths, dashboard hostname and user/group IDs with your own values. Both folders
must already exist, must be separate, and must have the permissions described
above. The image below follows the stable release channel; numbered release tags
are available if you need to pin a version or roll back.

The example uses Linux host paths. When running Compose from Windows PowerShell,
replace them with existing Windows paths such as `"D:/Media"` and
`"E:/MuxMender-Output"`. The container paths stay `/media` and `/output`.
For access from the same PC, set `MUXMENDER_ALLOWED_HOSTS` to `localhost:8767`
and open `http://localhost:8767/`. Windows folder access is managed through
Windows/Docker Desktop permissions, not by changing a Windows folder's UID.

```yaml
services:
  muxmender:
    image: ghcr.io/hysel/muxmender:stable
    user: "568:568"
    restart: unless-stopped
    ports:
      - "8767:8765"
    environment:
      MUXMENDER_CONTROLS_ENABLED: "true"
      MUXMENDER_ALLOWED_HOSTS: "YOUR-SERVER:8767"
      MUXMENDER_PLAYBACK_CODECS: "hevc,av1"
      NVIDIA_DRIVER_CAPABILITIES: "compute,video,utility,graphics"
    volumes:
      - type: bind
        source: /srv/media
        target: /media
        read_only: true
        bind:
          create_host_path: false
      - type: bind
        source: /srv/muxmender-output
        target: /output
        bind:
          create_host_path: false
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]
```

On a multi-GPU server, replace `count: 1` with `device_ids: ["YOUR-GPU-UUID"]`
to select a particular card. Find its UUID with `nvidia-smi -L`. Do not set both
`count` and `device_ids`; see [Docker's GPU Compose instructions](https://docs.docker.com/compose/how-tos/gpu-support/).

From the directory containing `compose.yaml`, run:

```sh
docker compose config --quiet
docker compose pull
docker compose up -d
docker compose logs --tail=100 muxmender
```

Use `sudo` if your Docker installation requires it. Open
**`http://YOUR-SERVER:8767/`**, select media under `/media`, and start with
**Create smaller copies**. Converted copies and history stay in your host output
folder when the container is recreated.

### First-run checks and updates

- **Keep the dashboard private.** It has no built-in login. Use a trusted LAN,
  VPN or authenticated reverse proxy; do not expose its port directly to the internet.
- **Replacement is optional.** After testing playback, make the `/media` mount
  writable and grant the app user write access if you want to use **Convert and
  replace originals**. No second replacement folder is needed. A writable mount
  alone does not enable replacement; you must choose it in the app.
- **Keep `/output` persistent.** It is needed even when replacing originals.
  Do not delete it to reset a queue: it contains history and recovery records.
- **Path does not exist?** Check each host-side storage path. Old optional GPU
  monitor mounts are not required for basic conversion; do not copy a stale
  monitor path from an earlier installation. GPU sharing has its own
  [monitor setup instructions](docs/gpu-monitor-setup.md).
- **Permission denied?** Check the numeric app user/group and folder access.
  **Blocked dashboard address?** Check that allowed hosts includes the exact
  browser hostname or IP and host port.
- **Updating:** pause new starts and let active jobs finish. Keep the same mounts,
  user, port and GPU assignment. Keep the tag set to `stable`. On TrueNAS, check
  for image updates and apply the offered update; with Compose, run
  `docker compose pull` and `docker compose up -d`. For TrueNAS update
  notifications, follow [stable-channel setup](docs/stable-updates.md).
  An interrupted job is not guaranteed to resume at the exact frame.

If TrueNAS does not offer an update, check that the new image has actually been
published to `stable`. A successful GitHub build, draft release or merged change
does not mean it is available yet. Keep the same repository and tag; you do not
need to build it yourself. See [update troubleshooting](docs/stable-updates.md#if-no-update-appears).

## How it works

1. Choose a video or folder. Subfolders are included by default.
2. Choose what to do: inspect, test a short clip, make a converted copy, or replace
   the original after successful checks.
3. Set your quality and savings targets, or use automatic encoding selection.
4. Follow the current step and read the result: converted, kept, or needs attention.

**“Inspection complete” means the file was inspected, not converted.** Inspection
does not save disk space. Sample testing also stops before full conversion.
Choose **Create smaller copies** or **Convert and replace originals** to request
full conversion. See [what each action does](docs/GETTING-STARTED.md#choose-the-right-action).

The app compares supported HEVC/H.265 and AV1 options. It preserves the original
resolution by default and checks audio, subtitles, chapters and HDR information
where supported. Not every video will get smaller, and lossy encoding cannot
promise an identical picture.

Development also includes optional [resolution and bitrate presets](docs/output-presets.md).
New jobs can choose Strict, Balanced or Space saver quality checks. Balanced is
the default; all three keep the timing, audio, subtitle and size checks in place.
Lower-resolution copies lose detail intentionally; they are checked against a
reference resized to that resolution. GPU and HDR transformations still need
qualification before release. Original resolution remains the default.

## You decide what happens to the original

**Safe-copy mode keeps it. Replacement mode permanently removes it only after
the new file passes validation and is verified in its destination.**

Choose safe-copy mode if you are unsure. Converted copies take extra space until
you remove or replace the original. Lifetime savings count confirmed replacements;
snapshots and retained work files can still occupy disk space.

The app uses a separate output folder for work in progress and job records.
After verified replacement, eligible generated files can be
[cleaned automatically](docs/replacement-cleanup.md). Active work and safe-copy
outputs are not swept away.

## Start with a small test

The [getting-started guide](docs/GETTING-STARTED.md) walks through the app.
Open the dashboard, choose a few videos, select **Create smaller copies**, and
add them to the queue. Read the results and check playback before choosing
replacement. No processing commands or scripts are needed.

## Existing audio issues

Existing audio decoding issues, including CRC errors, do not by themselves stop
MuxMender from making the video smaller. The original compressed audio is kept
unchanged, and the result warns you that its existing issues remain. MuxMender
does not repair, drop, or re-encode the damaged audio. It may still glitch during
playback, just as the original can.

Every copied audio packet and its timing must pass preservation checks. Unreadable
tracks, changed audio, video-quality failures, and insufficient savings still
prevent replacement.

## What has been tested?

Some container read errors can be handled without changing the source. The
app can use a byte-verified temporary copy when stray bytes follow
a complete Matroska container. Results explain when this happened. The converted
file must still pass the normal quality, timing and copied-track checks; see
[container warnings](docs/wiki/Results.md#warnings-about-the-container).

Selected SDR, HDR10, legacy AVI and DVD-rip workflows have passed project tests.
Results depend on the input, GPU, driver, encoder and player—not just the file
extension. See [tested formats](docs/TESTED-FORMATS.md) for the scope and limits.

The current shared engine includes NVIDIA Dolby Vision and combined
Dolby Vision/HDR10+ routes. Acceptance and replacement depend on each file's
preservation, quality and savings evidence. These are not universally certified
formats. See the [current use-case inventory](docs/SUPPORTED-USE-CASES.md),
including known failures and the distinction between automatic and research use.

The [release notes](https://github.com/hysel/MuxMender/releases) describe what is
available in each published image. Merging code does not update a running app.
You can also open **Release notes** beside the installed version at the bottom
of the dashboard. Read the notes for the new version before applying an update;
TrueNAS custom-app image updates may not display them in the update dialog.

For storage maintenance, see [what remains after a task](docs/post-task-cleanup.md).
Keep history and
recovery records; don't delete the whole output folder to clear old test files.

## Responsible use

**We do not support piracy.** Only process media you have the rights or permission
to use. Do not use MuxMender to obtain or share unauthorized copies. This project
is for optimizing an existing library, not downloading content or bypassing DRM.

## Source and support

This repository also contains the app source and essential deployment infrastructure.
Development test suites and experimental tools are maintained separately; they
are not installation or everyday-use steps.
For help, open an issue with the app version and sanitized error details; leave
out private paths and video names.

### Restart cancelled work (next release)

After cancellation finishes, **Restart cancelled jobs** lets you review and
restart the last cancelled queue with its previous settings. Completed work stays
completed. Encoding starts again for an interrupted video; history is retained.
See [Manage the queue](docs/wiki/Queue.md) for exclusions and approved-copy behavior.
