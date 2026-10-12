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

The revised image passed runtime and generated NVIDIA checks on 12 October.
Its digest is `sha256:e57d69f29e4c6d144cce5a3ab0be79f3afc56d165a4d8f35d89acd3760a2a9ec`.
The separate scanner is bound to that digest, not its mutable image tag. Its
completed rescan reported 22 findings: 16 medium and six low. Comparing package
and vulnerability identifiers confirms the six missing findings are the five
pip findings and one wheel finding. Neither package has a finding in the new
report. No high or critical findings were reported.

The later notice-bearing image
`sha256:20bceb9acd80f3bcf9e6a81312f4eede6d576b06fab978ab48e5da48f10c8c04`
retains identical versions for all 148 installed packages and identical hashes
for the three inventoried FFmpeg/readers. The build reused its runtime layers.
This carries forward the earlier runtime findings; it is not described as a
fresh security scan of the new digest. Remaining medium/low findings are retained
in the preview disclosure, not suppressed or treated as fixed.

The PyAV native-library provenance check now covers all 32 ELF code sections:
26 match the upstream build and six match checksum-verified distribution RPMs
with the collected source RPM identities. This strengthens source matching,
not vulnerability detection or whole-file reproducible-build certification.

This is a verified improvement, not full release clearance. Exact dependency
materials have been refreshed and the revised image passed its generated-file
service lifecycle. Custom native-library coverage and remaining findings still
need review.

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
is a failed test interception, not a pass. Both cancellation and recreation passed
on 12 October against both the r2 and revised r3 candidates. The revised candidate
also passed safe-copy conversion and recreation with retained output hashes and
history. These tests mounted no library media and did not restart production.
They do not establish anonymous public installation or real-library replacement
qualification.
