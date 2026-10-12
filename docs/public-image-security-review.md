# Public image security review

## What the first scan found

The 12 October 2026 scan of the exact r2 candidate reported 28 package findings:
21 medium and seven low, covering 22 distinct vulnerability identifiers. It
reported no high or critical findings and listed no fixed package versions.
That is a report of scanner coverage, not proof that every embedded library is
safe. Original reports and the software inventory are retained outside Git.

## Changes prepared

Five findings concern pip and one concerns wheel. These are build tools, not
services required by the app. The public Dockerfile now installs the pinned PyAV
wheel in a separate stage and copies only its installed runtime into the final
image. It keeps hash verification and does not alter conversion or quality checks.
Deleting pip in a later layer would leave its files in distributed earlier layers;
the separate stage avoids adding those installer layers to the final image.

This revised recipe is not yet image-qualified. We must rebuild it, repeat
runtime/GPU/service checks, recollect its exact dependency materials and scan the
new image. Do not subtract six findings from the release report until a new scan
confirms what is actually shipped.

Ubuntu's [pip advisory](https://ubuntu.com/security/CVE-2024-35195) distinguishes
the standard package from an Ubuntu Pro fix. A missing scanner `FixedVersion`
does not mean no fix exists anywhere. We are not adding subscription credentials
or assuming that commercial-package redistribution is approved.

## Still open

- Review required parser and codec libraries rather than removing functions the
  app needs. Keep malformed-input rejection and unprivileged execution.
- Compare the next installed Ubuntu versions with vendor advisories. Do not
  silently suppress findings because the process is unprivileged.
- Check the manually built FFmpeg/reader, FEL runtime and PyAV's embedded native
  libraries against the source inventory. Package-manager scanning alone is not
  complete coverage of custom binaries.
- Record the final image digest, scan date and disposition of remaining findings
  before deciding whether to publish. No public image is approved yet.

## Cancellation qualification

The isolated cancellation test uses generated video and the normal app API. It
requires an observed native media subprocess before cancelling, then checks that
the subprocess disappears, the queue pauses, the source stays unchanged and the
cancelled history survives container recreation. Finishing before cancellation
is a failed test interception, not a pass. The test is staged for administrator
execution and does not mount library media or restart production.
