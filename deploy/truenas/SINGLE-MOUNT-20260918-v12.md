# Single media mount

Supersedes the two-mount instructions in v11. No `/media-replace` mount is needed.
The app ignores `MUXMENDER_REPLACEMENT_ROOT`; the replacement target is `/media`.

## Deploy

```sh
sudo docker build -f /mnt/FR4G/Apps/muxmender/app-build-20260918-v12/deploy/truenas/Dockerfile.app -t muxmender-app:20260918-v12 /mnt/FR4G/Apps/muxmender/app-build-20260918-v12
```

Wait for active jobs to finish, then set tag `20260918-v12` and:

- Keep the existing media host path mounted at `/media`; turn OFF Read Only.
- Set `MUXMENDER_REPLACEMENT_ENABLED=true`.
- Remove `MUXMENDER_REPLACEMENT_ROOT` and the extra `/media-replace` mount if added.
- Keep `/output`, GPU assignments and remaining settings unchanged.
- The app user needs write/delete permissions on target media directories.

Copy-only installations retain a read-only `/media` mount and leave replacement
disabled. Writable media without explicit replacement opt-in is rejected. Preview,
submission and execution recheck the access policy. Copy jobs on writable media
still only produce separate outputs; only confirmed replace jobs publish them.

Full validation, source/output/staged/final hashes and recovery journal safeguards
are unchanged. MKV-only replacement and retained-output storage caveats still apply.
There is no login: restrict network access to trusted users who may delete originals.
