# Shared implementation requirement

The standalone CLI and TrueNAS app are frontends to shared media services.
Development tests, research tools and the experimental D3D11 helper are maintained
in the local development archive, not the published tree. Only essential build,
audit and publication helpers belong under deploy/. Run the external qualification
suite before release approval; a hosted build alone is not full qualification.
Do not implement a separate app-specific codec, naming, quality, metadata,
cleanup, capability or publication policy. Reuse/extract the shared implementation
and add parity tests when exposing a feature through another frontend.

Automatic job arguments live in `python/media_workflow.py`; the processing engine
is `python/auto_optimize.py`. Naming and reviewed rename transactions live in
`python/media_naming.py`. Publication stays in `python/validated_replace.py`.
Legacy specialized routes are not equivalent to automatic conversion; preserve
their guards and evidence until migrated to shared orchestration. Do not claim
integration or hardware qualification merely because a module ships in Docker.

No media changes during refactoring tests: use generated fixtures. Do not change
the running app, resume a queue, or create a Docker release unless requested.
Ask before git commit, merge or push. Preserve unrelated user changes.

# Continue until completion or required user input

Keep working on the authorized task until it is complete. Do not stop between
steps or require the user to type "next", "continue", or repeat an approval
already given. Progress updates are not stopping points: report briefly and
continue executing, testing, investigating failures, and verifying the result.

While a test or background job runs, continue other safe, in-scope work and
monitor the job through completion using the available tools. Starting a job
is not the same as completing the task. Do not claim ongoing monitoring unless
an actual monitoring process is running.

Pause unfinished work only when user input, a decision, credentials, or required
approval is genuinely necessary, or when the user asks to stop. Explain the
specific blocker and ask for exactly what is needed. If the answer blocks only
one part of the task, continue the other authorized work where possible.
Persistence does not expand permission: retain all safety, quality, preservation,
commit, publication, and deployment requirements in this file.

# Resolve known errors before committing

When an error is discovered, fix it and verify the fix before committing.
This includes older failures uncovered during review, not only the newest error.
Maintain an explicit list of discovered errors and their verification status;
do not treat a historical failure as resolved without supporting evidence.
Do not commit, push, merge, or publish while known errors remain unresolved.
If an error cannot be resolved, explain the blocker and obtain the user's
explicit approval to defer that specific error before proceeding. General
approval to commit or release does not authorize deferring known errors.
Never bypass quality or preservation checks merely to make a failure disappear.

# Automatic reader compatibility

Increment `reader_qualification_cache.POLICY_VERSION` when changing reader proof
requirements, field comparisons or the meaning of damaged-input controls. Verify
that old successful evidence is rechecked automatically, including administrator
receipts. Ordinary app updates may reuse unchanged valid proofs; failed self-tests
must be retried after an app update without requiring a host script.

# Existing source audio issues

Existing audio decoding defects (including CRC errors) are reported warnings,
not a reason by themselves to block video size reduction. Preserve the original
compressed audio unchanged; never conceal, drop, repair, or re-encode it silently.
Approval still requires complete copied-packet and timing verification plus the
normal video quality, metadata and savings checks. Unreadable tracks, newly
introduced audio changes, video errors and infrastructure failures remain blocking.
Keep the source-audio warning in results and replacement receipts. Distinguish
preservation of an existing defect from clean audio decoding or an audio repair.

# Fix and upstream compatibility records

Keep developer fix ledgers and research evidence in the local development archive,
outside the published repository, with implementation, regression tests, evidence
and qualification limits. The docs directory is only for installation,
configuration and UI use. Keep withdrawn experiments
and unresolved cases distinct from verified fixes. Build the reusable FFmpeg
test package for proposed runtime upgrades. Do not retire a workaround solely
because a newer version exists or managed tests pass: require an old-runtime raw
reproducer, new-runtime raw success, unchanged negative/preservation checks and
representative full-file qualification. Safety gates are not workarounds.

# Development run visibility

Never execute Linux remote-reader payloads or signal-based process probes on
this Windows host. In particular, never call `os.kill(pid, 0)` here: Windows
console signaling can interrupt the coding session. Run remote-reader tests on
Linux, use read-only `/proc` checks there, and retain explicit platform guards.

Every long development, qualification or benchmark run must have a persistent
tracked job and appear on the development dashboard before being left running.
For remote jobs, register a live read-only observer (the research monitor supports
both batch and tracked jobs), verify its entry through the dashboard API, and
report the dashboard URL. Keep current-stage progress separate from total work.
Connection loss must show stale/unavailable, never imply completion. Record the
final result and preserve it after the observer exits. Do not hide development
jobs among production queue items or count test copies as reclaimed disk space.

# Repository privacy

Keep Git source-only: code, generated-fixture test definitions, configuration,
build scripts, documentation and required license notices. Do not commit media,
screenshots, compiled binaries, downloaded dependencies, archives or run outputs.
Store release/dependency bundles outside the checkout. Do not remove required
licenses or rebuild sources merely to reduce package size. CI checks the tracked
working tree; this is not a historical Git-object audit.

Do not name real movies, series, episodes, or identifiable media release filenames
in code, tests, configuration, documentation, example commands, filenames, or
commit messages. Use neutral case
identifiers and placeholder paths. Preserve technical results and qualification
limits. Historical media-path examples are anonymized, not exact runtime locators;
never rename actual media or alter runtime evidence just to sanitize documentation.
