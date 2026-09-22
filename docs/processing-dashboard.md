# Processing dashboard (pending deployment)

Top-level automatic workflow stages are emitted by the shared processing engine,
not guessed from a percentage: inspect, compare, encode, validate, publish, cleanup.
Individual checks keep their independent percentages and ETAs. A completed check
does not imply a completed stage or job, and stage position is never converted
into an estimated overall percent.

The dashboard appears before lifetime savings and setup. Every active video has
a compact numbered workflow, highlighted current step, current-check percentage
or an explicit measuring state, elapsed time and check ETA when available. Unknown
legacy telemetry is labeled rather than assigned a fabricated stage. Technical
details and resource settings are expandable. Original-keeping modes omit
publication/cleanup stages. Failed/skipped outcomes remain outcomes, not success.

The same stage metadata is available to the CLI job catalog and TrueNAS UI.
No deployed image, queue or media is changed by this implementation.
