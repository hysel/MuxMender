# Update the app

Use repository **ghcr.io/hysel/muxmender** and tag **stable**. This downloads the
published image; you do not need to build it on your server.

## TrueNAS

1. Enable Docker image update checks and allow image downloads (not Never pull).
2. Pause new starts and let active work finish.
3. Apply the image update when TrueNAS offers it.
4. Keep the existing folders, user, GPU assignment and port settings.
5. Open the dashboard and check your history and queue before resuming.

Update discovery is periodic, not instant. A source-code commit is not an image
release. The stable tag changes only after publication and promotion.

## Standalone Docker

Pull the new stable image and recreate the container with the same configuration.
Keep media and output in persistent host folders. See the
[installation instructions](../README.md#install-with-standalone-docker).

## If you need to go back

Select a previous published numbered image tag, retain your persistent folders,
and check the release's rollback notes. Stop active work first. An interrupted
job may need recovery or a retry; exact-frame continuation is not guaranteed.

An Always pull policy may fetch a new stable image when the container is recreated.
Use a numbered tag instead if you want a strictly pinned version.
