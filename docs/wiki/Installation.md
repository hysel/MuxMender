# Set up the app

MuxMender runs as a container with its own browser interface. The first release
path focuses on Linux and NVIDIA GPUs. You choose which GPU and folders the app
can access; it doesn't install a driver on your server.

For complete, copyable setup instructions, see the README's
[TrueNAS installation](../../README.md#install-on-truenas) or
[standalone Docker installation](../../README.md#install-with-standalone-docker).

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
the Never pull policy; see [stable-channel setup](../stable-updates.md).

An interrupted job may need recovery or a retry; it doesn't necessarily resume
at the exact frame where it stopped. Don't delete its work folder while the app
is recovering it.

## Which image should I install?

Use **`ghcr.io/hysel/muxmender:stable`** for the stable release channel.
No registry login is required. Read the
[release notes](https://github.com/hysel/MuxMender/releases)
before installing; the app targets Linux amd64 with NVIDIA GPU access.
Numbered release tags remain available for pinning or rollback.

The release includes `compose.release.yaml`. Replace every `REPLACE_*` value
with your own settings and use `stable` for `REPLACE_RELEASE_VERSION`.
Create the host folders first and grant the selected user access. The template
keeps your media read-only for the first safe-copy run.

Source/build archives and third-party notices are also available on the release
page. You do not need those archives in `/media` or `/output` to use the app.
