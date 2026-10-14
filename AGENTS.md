# Shared implementation requirement

The standalone CLI and TrueNAS app are frontends to shared media services.
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

# Fix and upstream compatibility records

Record each new fix family in `docs/fix-ledger.json`, with implementation,
regression tests, evidence and qualification limits. Keep withdrawn experiments
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
