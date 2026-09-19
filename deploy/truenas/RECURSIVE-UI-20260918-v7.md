# Recursive folder selection by default

Both the video dropdown and processing preview include all subfolders by
default. The visible Folder scope selector offers This folder only — one level.
Changing scope reloads the video list and invalidates any previous preview.
Nested video names show relative paths. Selecting an individual video still
processes just that file. Original protection and the 100-video request limit
are unchanged; choose smaller folders for larger libraries.

```sh
sudo docker build -f /mnt/FR4G/Apps/muxmender/app-build-20260918-v7/deploy/truenas/Dockerfile.app \
  -t muxmender-app:20260918-v7 /mnt/FR4G/Apps/muxmender/app-build-20260918-v7
```

After active work finishes, change the app image tag to `20260918-v7`, retain
all existing v6 settings, and refresh the browser. No job is started by this
update. Controls remain enabled; legacy autonomous scanning remains disabled.
