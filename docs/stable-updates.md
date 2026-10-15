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

## If no update appears

Check that the repository is `ghcr.io/hysel/muxmender`, the tag is `stable`, and
image update checks and downloads are enabled. A numbered tag stays on that
release; it does not follow `stable`.

A green GitHub build or a draft release is not an update announcement. The image
still needs its release checks and publication. If it has not reached `stable`,
there is nothing for TrueNAS to download yet. You do not need to build the image
yourself or install the maintainers' test tools.

Faster image builds make releases quicker to prepare. They do not, by themselves,
make video conversion faster. Check the release notes for changes that affect
processing speed.

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
