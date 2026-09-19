# Workspace usability fixes

- Progress precedes setup; compact heading replaces large promotional header.
- Results show the latest 100 UI requests, not legacy development runs. Counts say
  requests because an inspection and conversion of one source are separate jobs.
- Empty folders disable review and suggest including subfolders or changing folder.
- Pause and resume buttons reflect the queue state.
- Long filenames and details wrap; visually checked at 320px and 390px in Playwright.
- Unmeasured stages say percentage/ETA unavailable and show total job elapsed time.
  This does not invent progress or change the encoder's measurement capabilities.

Validation: 311 automated tests run, 3 platform-specific skips. Read-only local
preview used live GET data; no extra jobs submitted and no production job restarted.
Playwright verified narrow layouts, dark appearance, empty-folder behavior and
disabled resume. Preview's only console error was its missing favicon.

```sh
sudo docker build -f /mnt/FR4G/Apps/muxmender/app-build-20260918-v10/deploy/truenas/Dockerfile.app -t muxmender-app:20260918-v10 /mnt/FR4G/Apps/muxmender/app-build-20260918-v10
```

After active jobs finish, set the existing app image tag to `20260918-v10`.
Retain all other settings. No media files or persisted queue records are changed.
