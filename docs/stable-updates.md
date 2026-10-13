# Update through TrueNAS

MuxMender's `stable` channel is a moving alias for a reviewed, qualified release.
Numbered tags remain unchanged so you can pin or roll back a version. Stable
promotion never rebuilds the image and does not update a running app.

Once the first promotion is published and verified, configure the custom app:

- Repository: `ghcr.io/hysel/muxmender`
- Tag: `stable`
- Enable TrueNAS Docker image update checks.
- Use a pull policy that permits downloads, not Never pull.

Keep your existing storage mounts and GPU assignment. Let active jobs finish
before using TrueNAS's Update action: updating restarts the container. A moving
tag also means an Always pull policy may fetch a new release on recreation, not
only when you intentionally check for updates. Use a numbered tag if you need
strictly pinned behavior. Update discovery is periodic, not instant.

[Automatic upgrade recovery](upgrade-recovery.md) has a graceful-shutdown retry
implementation in development. Stage checkpoints and container-upgrade qualification
remain pending; let active jobs finish before updating the installed release.

## Publishing a stable update

First publish and anonymously verify the numbered image using the existing
qualified-image workflow. Then run **Promote tested image to stable** on main,
supplying the version, verified registry manifest digest and review-asset hash.
Approve the `container-release` environment in GitHub. The workflow checks the
release record, copies the identical registry manifest to `stable`, and verifies
the result. No TrueNAS credentials, media mounts or Docker host access are used.

Recheck the stable digest anonymously before telling users an update is ready.
The channel is approval-driven; merging code alone does not move it. The name
describes the tested update channel, not a guarantee for every GPU or video.

See [TrueNAS image update settings](https://apps.truenas.com/getting-started/initial-setup/)
and [custom app image settings](https://www.truenas.com/docs/scale/apps/installcustomappscreens/).
