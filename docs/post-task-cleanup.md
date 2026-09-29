# What remains after a task

The shared automatic workflow now finalizes temporary files after a normal
return, processing error, or graceful cancellation. The same policy covers SDR,
HDR and the shared single-/dual-layer Dolby Vision paths, in CLI and app use.

| Outcome | Kept | Removed |
| --- | --- | --- |
| Original kept: size or quality rejection | Original, small result/history records and logs | Generated media, extracted layers and bulky frame/packet/quality data |
| Error or graceful cancellation | Original, error and cleanup records | Owned generated work, provided the source still exists and no recovery transaction needs it |
| Successful full safe copy | Final output plus original and result records | Other candidates, extracted streams and bulky validation data |
| Successful sample test | Selected output samples and recorded references | Other candidates and intermediate validation data |
| Verified replacement | Published media and receipts | Generated work, only after the existing receipt/hash and recovery checks |
| Explicit full-copy research | Requested research output and summary | Intermediate layers and per-frame metrics; failed research copies are not approved replacements |

RPU binary exports and the large per-frame layer metadata JSON are temporary
artifacts too. Small quality summaries, decisions, errors and cleanup receipts
remain available for reports. Cleanup never weakens conversion quality checks.

New shared command outputs also have a generated-artifact manifest, so an unknown
extension does not automatically leave large working files behind. Entries are
restricted to owned work paths and checked for changes before cleanup. Additional
audio intermediates, including TrueHD and MKA files, use the shared cleanup policy.
Startup reconciles known terminal jobs; it does not sweep abruptly killed active
jobs or publication-recovery files.

There are intentional safety stops: an active/unknown state, missing source,
missing deliverable, linked path, external hardlink, or replacement recovery
journal can prevent deletion. Older successful sample records without explicit
output paths are retained rather than guessing which file is the deliverable.

A forced kill, power loss or filesystem failure can prevent any finalizer from
running. The app reports incomplete cleanup instead of silently declaring space
reclaimed. It does not blindly sweep potentially active/recoverable files at
startup. Use the guarded recovery/cleanup review for those cases.

This policy applies to shared automatic workflows. Historical standalone research
scripts and legacy preview tools must not be assumed to have the same finalizer.
