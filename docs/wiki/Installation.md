# Set up the app

MuxMender runs as a Linux amd64 Docker container with its own browser interface.
It is not limited to TrueNAS: Linux Docker hosts and Windows Docker Desktop
with the WSL 2 Linux-container backend are deployment options. The current release
targets NVIDIA GPUs. You choose which GPU and folders the app can access; it
doesn't install a driver on your host. End-to-end qualification currently covers
Linux/TrueNAS, not Windows Docker Desktop.

For complete, copyable setup instructions, see the README's
[TrueNAS installation](https://github.com/hysel/MuxMender#install-on-truenas) or
[standalone Docker installation](https://github.com/hysel/MuxMender#install-with-standalone-docker).

Install the ready-built image from GitHub Container Registry. You do not need to
clone this repository, build on TrueNAS or run a release script. After installation,
select files, choose settings, manage the queue and review results in the browser.
Maintainers run release checks separately. You do not need research containers,
qualification scripts or administrator helper commands for everyday use.
GPU inspection compatibility is checked automatically inside the app. Keep the
output storage persistent so saved checks and job history survive upgrades.

## What you need

- A working NVIDIA driver and GPU access for containers.
- A media folder containing your existing videos.
- A separate, persistent output folder for work files, converted copies and history.
- Enough free space for conversions in progress. Replacing a video still needs
  room for the new file before the original can be removed.

The output folder must not sit inside the media folder, or vice versa. Keep both
outside the container so an image update doesn't remove your files or history.

## Install on TrueNAS

1. Create the output folder on your storage pool. Give the app's configured
   user permission to write to it.
2. Create a custom app using the release's installation instructions. Use the
   `ghcr.io/hysel/muxmender` repository with tag `stable`.
3. Mount your library at **`/media`** and the output folder at **`/output`**.
4. Assign an NVIDIA GPU using TrueNAS app settings. Don't paste another user's
   GPU identifier into your configuration.
5. Choose a dashboard host port. The container listens on **8765** by default.
   For example, host port **8767** can map to container port **8765**.
6. Configure the app's portal link with the **host port**, then start the app.
7. Open `http://YOUR-SERVER:8767/` if you used that example port.

For copy-only use, a read-only media mount gives extra protection. Replacement
requires a writable media mount and write permission for the app user. A
writable mount alone doesn't authorize replacement: you still choose the action
in the UI.

The app also needs its allowed dashboard addresses configured. These are
`hostname:port` entries matching the address you open, not wildcard values.
Follow the release template for enabling the UI controls; older one-shot and
research templates are not the everyday app configuration.

## Keep access private

The dashboard currently has no login. Keep it on a trusted network. Don't
forward its port directly to the internet. For access away from home, use a
secured VPN or an authenticated gateway.

## Update later

Pause new starts and let active work finish before updating. Keep your media and
output mounts, app user, GPU assignment and port settings. Keep the tag set to
`stable`, check for image updates in TrueNAS, and apply the offered update. Then
check that your history and queue appear. Enable image update checks and avoid
the Never pull policy; see
[stable-channel setup](https://github.com/hysel/MuxMender/blob/main/docs/stable-updates.md).

In TrueNAS, use the app's image-update action when a new stable image is available.
Do not change the tag for each update. Docker-based installations pull the new
`stable` image and recreate the container using the same configuration. This is
an image download, not a source build. Updates appear only after a release is
published and promoted; a repository commit alone does not produce an update.

An interrupted job may need recovery or a retry; it doesn't necessarily resume
at the exact frame where it stopped. Don't delete its work folder while the app
is recovering it.

## Which image should I install?

Use **`ghcr.io/hysel/muxmender:stable`** for the stable release channel.
No registry login is required. Read the
[release notes](https://github.com/hysel/MuxMender/releases)
before installing; the image uses Linux amd64 with NVIDIA GPU access, even when
the host runs Windows. See the README for Windows setup and qualification limits.
Numbered release tags remain available for pinning or rollback.

## What changed in an update?

Choose **Release notes** beside the version at the bottom of MuxMender to read
about your installed version. Before updating, open
[GitHub releases](https://github.com/hysel/MuxMender/releases) and read the notes
for the new version. They cover features, fixes, performance changes, required
steps and known issues. TrueNAS custom-app image updates may not show this link
in their own update dialog.

The release includes `compose.release.yaml`. Replace every `REPLACE_*` value
with your own settings and use `stable` for `REPLACE_RELEASE_VERSION`.
Create the host folders first and grant the selected user access. The template
keeps your media read-only for the first safe-copy run.

Source/build archives and third-party notices are also available on the release
page. You do not need those archives in `/media` or `/output` to use the app.
