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

# Repository privacy

Do not name real movies, series, episodes, or identifiable media release filenames
in code, tests, configuration, documentation, example commands, filenames, or
commit messages. Use neutral case
identifiers and placeholder paths. Preserve technical results and qualification
limits. Historical media-path examples are anonymized, not exact runtime locators;
never rename actual media or alter runtime evidence just to sanitize documentation.
