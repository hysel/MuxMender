# Active fixes and simpler workspace

Development work only. Production stays paused, source files stay untouched,
and quality requirements stay unchanged. Publication and deployment need approval.

## Ordered work

1. **Reconciled:** last v41 run: 5 replacements, 5 keeps, 11 failures. The
   failures comprise 5 TrueHD decode errors, 2 AV1 timing cases, 3 resource-wait
   timeouts, and 1 combined dynamic-HDR metadata case.
2. **Implemented, qualification pending:** the full-file service accepts a
   source/settings/quality-bound shared decision. Direct standalone callers
   retain their own preflight. All 48 targeted Linux regressions passed.
3. **In progress:** full HDR copy qualification with unchanged quality and preservation.
   The run reached full encoding but unlimited mux buffering exceeded its 1 GiB
   guard. Specific failure reporting and guard tests passed. The finite-buffer
   experiment preserved all packets at 35.5 MiB peak but failed seeking, so that
   mux change was withdrawn. Alternative mux qualification passed at 108.6 MiB
   peak with exact packet/clock preservation and six successful seek checks.
   The shared integration passed 71 Linux tests; full conversion qualification
   is running again. No buffer-limit increase or production deployment.
4. Pending: source-faithful AV1 interior sampling with decoder context.
5. Pending: TrueHD decoder/source diagnosis and evidence-backed recovery.
6. Pending: concurrent validation waits, cancellation and recovery qualification.
7. Pending: redundant trial failure audit.
8. Pending: review the five size/quality keeps.
9. Pending: faster evidence-based early decisions.
10. Pending: stage-progress audit and redesigned live workspace.
11. Pending: redesigned results and activity reporting.
12. Pending: terminal-work cleanup audit.
13. Pending: restart, retry and history behavior.
14. Pending: shared-engine regression suite and UI accessibility checks.
15. Pending: documentation, evidence matrix and release handoff (not deployment).

Unresolved items retain their diagnosis and next experiment; a blocked case is
not counted as fixed. Tests and long-running experiments appear on the development
dashboard. No actual storage savings are credited to retained research copies.

## UI redesign brief

Rebuild the presentation around three places rather than a long page of panels:

- **Overview:** lifetime confirmed savings always first, then current work,
  a compact resource summary, and one obvious action to add videos.
- **Add videos:** select a folder or files, confirm the selection (subfolders
  included by default), choose the action, and start. Show everyday settings;
  disclose codec, resource and advanced controls only when requested.
- **Results:** readable outcome groups and a short table with completion time,
  source/output size, saved amount, and a plain-language reason. Search, filters,
  technical evidence and individual details expand on demand.

After a successful queue submission, show current work rather than leaving the
setup form expanded. Keep the selected folder available for later edits. Preserve
all supported controls, replacement confirmation, pause/resume and retry semantics.
Never imply a running task has completed because its current step reached 100%.

Use accessible light/dark/system themes, semantic headings and controls, visible
keyboard focus, labelled inputs, non-color status cues, reduced-motion support,
and responsive layouts. Verify keyboard and screen-reader semantics and contrast;
do not claim formal Section 508 certification from an automated test alone.
No backend policy fork or new conversion behavior belongs in the UI layer.
