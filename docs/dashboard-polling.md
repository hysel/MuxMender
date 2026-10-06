# Reliable live progress

The next-release dashboard API serves its last-known catalog immediately. A
single background refresh discovers historical artifacts roughly every 30
seconds (or sooner when a known job finishes), rather than making each browser
request wait for a recursive scan.
Between discoveries, refreshes read only the small heartbeat records of known
running jobs. New jobs and final outcomes can take one discovery cycle to appear.

The first response may show “loading job progress.” Failed refreshes retain old
records and report that they are last-known data. Worker timestamps are never
advanced merely because the browser polled successfully; stale progress remains
visible as stale. Missing files or failed reads do not imply completion.

Both browser pollers allow only one in-flight request and tolerate responses up
to 30 seconds. Rendering failures are reported separately from network failures.
The queue and media-processing workers do not depend on an open dashboard.

The controls endpoint also returns its last snapshot immediately, using one
background refresh at a time. History reads run outside the queue mutex so
slow storage does not block queue actions. Responses include the snapshot time,
refresh state and error state. After fifteen seconds without a successful
refresh, the browser labels the status as delayed and disables queue controls
until a current snapshot returns. A successful HTTP response alone does not
make old queue data current. This controls change is prepared after v52 and
requires the next deployment.

Before this change, four live catalog requests took 12.5–14.1 seconds while the
browser abandoned requests after eight seconds. All four eventually returned
HTTP 200 with 474 records. This reproduced the misleading connection warnings.
The patch does not change processing limits, quality checks, or queued requests.

An isolated TrueNAS check against 488 real catalog records measured a 14.5-second
background discovery, initial cached poll calls below 1 ms and a populated poll
plus JSON serialization at 8.9 ms. Those are backend measurements, not a promise
about browser/network latency. Targeted Linux tests: 57 passed, five skipped;
local UI/navigation tests: 11 passed. This fix is not deployed in v45.
