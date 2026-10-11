# Fix ledger

This is our working list of fix families, not a promise that every route is
certified on every runtime. The [machine-readable ledger](fix-ledger.json) links
each item to its code, regression tests and recorded evidence. The reusable
[FFmpeg comparison package](ffmpeg-compatibility.md) includes the complete test
inventory as well as this list. New fixes must be added here and to the ledger.

“Implemented” means the code exists. “Targeted checks passed” means only the
recorded cases passed. Neither label approves an untested full conversion.

## Library behavior to check again after FFmpeg upgrades

| ID | What we handle | Current evidence |
| --- | --- | --- |
| FF-001 | AAC startup trimming when changing containers | Targeted checks passed |
| FF-002 | AAC non-zero start and final-packet representation | Implemented |
| FF-003 | Duplicate native MP4 chapter-text representation | Targeted checks passed |
| FF-004 | Redundant chapter parsing in audio/frame/packet readers | Targeted checks passed |
| FF-005 | Undeclared aspect ratio becomes explicit square pixels | Open; reproduced |
| FF-006 | Interior samples need correct source decoder context | Implemented |
| FF-007 | Missing final MPEG-4 Visual frame clock | Targeted generated checks passed |
| FF-008 | Copied-audio Matroska clock representation | Implemented |
| FF-009 | Decode-sink clock reset diagnostics | Implemented |
| FF-010 | Absolute end versus elapsed duration headers | Implemented |
| FF-011 | Preserve missing color declarations without inventing them | Implemented |
| FF-012 | AV1/HEVC chroma and content-light metadata | Implemented |
| FF-013 | Dolby Vision header/layer inspection | Limited qualification |
| FF-014 | Dolby Vision/HDR10+ preserved routes | Limited qualification |
| FF-015 | GPU reader timing and HDR evidence | Bound to qualified reader version |
| FF-016 | Native Matroska chapter endpoint evidence | Implemented |
| FF-017 | Copied-track relay and bounded mux buffering | Targeted checks passed |
| FF-018 | Restore a padded DTS terminal duration from exact source packet proof | Generated preservation checks passed on both runtimes; full-image quality rerun pending |

These are **review candidates**, not automatically removable code. Several also
contain preservation logic we need regardless of the library version. Retire only
the proven redundant part, after raw old/new tests, negative controls and full-file
qualification. Missing fixtures are coverage gaps—not upstream fixes.

## MuxMender behavior that a library upgrade does not replace

| ID | Fix family | Current state |
| --- | --- | --- |
| APP-001 | Carry verified chapters from admission into the conversion worker | Fixed; targeted remux passed; not deployed |
| APP-002 | Remove terminal scratch files while keeping receipts/history | Implemented |
| APP-003 | Cancel active worker groups safely | Implemented |
| APP-004 | Start an empty queue automatically; remove individual items | Implemented |
| APP-005 | Bind history to source identity; show retries/interruption honestly | Implemented |
| APP-006 | Resource Apply feedback and recovery from lost acknowledgement | Fixed; not deployed |
| APP-007 | Approve an existing validated copy without encoding again | Fixed; not deployed |
| APP-008 | Stage progress, timestamps, queue sizes and connection-loss feedback | Implemented |
| APP-009 | Hardware hints backed by actual runtime capability probes | Implemented |
| APP-010 | User-selected resolution, quality, HDR/SDR and savings settings | Implemented; qualification is route-specific |
| APP-011 | Embed VMAF models; retain exact GPU-reader diagnostic evidence | Corrected isolated recipe; full-image rerun pending |
| PERF-001 | GPU sharing and worker admission on a shared server | Implemented |
| PERF-002 | Validation concurrency and CPU thread budgets | Implemented |
| PERF-003 | Reuse evidence only when contents and settings match | Implemented |
| PERF-004 | Early efficiency decisions and bounded adaptive trials | Implemented |

## Checks and withdrawn experiments

APP-013 accepts Windows line endings in the app-version guard, normalizes shell
files in release archives, isolates revised build contexts by archive checksum,
and binds build status to that checksum. Regression checks pass; the revised
v60 image build is still required. No production deployment has occurred.

APP-012 attributes explicit video-decoder diagnostics encountered while opening
an input for audio preflight. It changes the engine evidence and readable UI
reason, not the decoder acceptance policy. Unit/UI regressions pass; source
track diagnostics are tracked separately. No production deployment is implied.

| ID | Item | Policy |
| --- | --- | --- |
| SAFE-001 | Quality, dimensions, timing, metadata and copied-track checks | Keep |
| SAFE-002 | Reject genuine source decoder errors | Keep; diagnose reported cases |
| SAFE-003 | Verified replacement, conflicts, journals and recovery | Keep |
| POL-001 | Widened timing/sample-window experiments | Withdrawn; not a deployed fix |

The ledger is backfilled from current code and repository evidence. The package
flags regression modules not yet assigned to a fix family so they remain visible
for follow-up rather than disappearing from the inventory.
