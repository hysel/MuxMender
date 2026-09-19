# End-user workspace

Replaces the development-oriented app page with a single workflow:

1. Choose a server folder (subfolders included by default), then all videos or one video.
2. Choose an action, optionally adjust advanced settings, and review the exact selection.
3. Start jobs and follow current-stage progress. Review per-video outcomes and reasons.

Removed duplicated history/queue displays, capability tables, environment configuration,
development navigation and diagnostic panels from the primary interface. Logs remain
available inside individual result details. Authentication, preview confirmation,
quality thresholds, read-only media and source-protection rules are unchanged.

Light, dark and system appearance; responsive layout; explicit field labels; skip link;
visible keyboard focus; focus return from folder selection; polite state announcements;
reduced-motion and forced-color support; independent pause for live display updates.
Results use text, not color alone. Automated checks are explicitly not a guarantee of
identical visual quality. File-size savings are not described as reclaimed disk space.

Accessibility target: modern WCAG AA practices alongside Revised Section 508, which
incorporates WCAG 2.0 AA: https://www.section508.gov/develop/applicability-conformance/
Modern reference: https://www.w3.org/TR/WCAG22/

Automated structural, DOM-model and theme contrast tests are included. This is not
formal Section 508 certification. Browser rendering, 200–400% zoom, keyboard-only and
screen-reader testing on the deployed app are still required; no connected browser
was available in this session. Open result details remain stable during background
updates; changing a result filter explicitly refreshes the list.

## Deploy

Build the staged context on TrueNAS:

```sh
sudo docker build -f /mnt/FR4G/Apps/muxmender/app-build-20260918-v8/deploy/truenas/Dockerfile.app -t muxmender-app:20260918-v8 /mnt/FR4G/Apps/muxmender/app-build-20260918-v8
```

Edit the existing custom app image tag to `20260918-v8`, retaining its current image
repository, mounts, GPU assignment, port, credentials and environment settings.
No media conversion, deletion or replacement is performed by this UI upgrade.
