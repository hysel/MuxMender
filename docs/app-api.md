# The app API

## Approving an existing safe copy (after v59)

Send `approve-copy-preview` with the finished request's `job_id`. Review the
returned original/copy sizes, destination and permanent-removal warning. Then
send `approve-copy-confirm` with the returned `confirmation_id` and
`"confirm": true`. Confirmation expires after two minutes and is single-use. Changed files,
unqualified copies, read-only media, active work on the source and recovery
journals block approval. The same request becomes a publication-only queue item;
no video is re-encoded. Full shared publication checks and cleanup still apply.
Do not blindly repeat confirmation after a timeout; read the request state first.

Resource-profile writes return the saved `profile`. Queue polling also returns
that in-memory value without waiting for historical filesystem or GPU readings.

The API comes with MuxMender. It uses the same address and port as the dashboard;
there is no second service to install. You do not need it to use the app. It is
there if you want to check progress or manage jobs from a script.

Open `/api` at your dashboard address to see the API version, app version and
available endpoints. API version 1 describes this discovery response; the other
endpoints use the existing dashboard request and response formats. This is not
a promise that every internal job field is a stable public schema.

| Request | What it does |
| --- | --- |
| `GET /api` | Lists the available endpoints; does not start work. |
| `GET /api/jobs` | Returns the latest catalog progress. |
| `GET /api/controls` | Returns queue state, request history and the control token. |
| `GET /api/media?path=.&videos=true&recursive=true` | Lists videos inside the media mount. Follow `next_offset` for another page. |
| `GET /api/request-log?id=<request-id>` | Returns the selected request's diagnostic log. |
| `POST /api/control` | Uses the same actions and safeguards as the UI. |

Queue, media, log and action endpoints require app controls to be enabled.
Discovery lists only endpoints available in the current service mode.

## Read progress

For example, in PowerShell:

```powershell
$base = 'http://nas:8767'
Invoke-RestMethod "$base/api"
Invoke-RestMethod "$base/api/controls" | Select-Object counts, paused, wait_reason
```

The catalog and queue are separate views. A failed or disconnected response does
not mean work has finished. Treat missing progress as unavailable, not zero.

## Change the queue

Writes require JSON, an Origin matching the dashboard's HTTP address and the
current `X-MuxMender-CSRF` token from `/api/controls`:

In the development version, preview settings also accept `output_preset`:
`original` (default), `tv1080`, `mobile720`, or `small480`, and `hdr_policy`:
`preserve` (default) or `sdr`. They are saved with the request and passed to the
same engine as CLI jobs. See [preset scope and quality checks](output-presets.md).
New previews also accept `quality_profile`: `strict` (95/90), `balanced`
(default, 94/90), or `space-saver` (90/90), expressed as mean / fifth-percentile
VMAF scores. This is independent of the encoder's `quality` tuning setting.
Existing queued jobs are not rewritten. Changed profiles invalidate automatic
keep decisions, but not completed replacements or explicit keep choices.
Storing an HDR choice does not imply that an unqualified transformation is
enabled: such a request retains the source with an explanation.

```powershell
$state = Invoke-RestMethod "$base/api/controls"
$headers = @{ Origin = $base; 'X-MuxMender-CSRF' = $state.csrf_token }
Invoke-RestMethod "$base/api/control" -Method Post -Headers $headers `
    -ContentType 'application/json' -Body '{"action":"pause"}'
```

Pause stops new starts; current work can finish. The API does not provide a
shortcut around conversion validation or replacement confirmation. To submit
work, first send `preview` with settings, review its returned file list, then
send `submit` with its `preview_id`. Replacement also requires `confirm_replace`.

Adding new videos to an empty queue starts processing automatically, even if the
empty queue was paused. Completed and cancelled jobs are history, not queued work.
Adding files to a manually paused queue with waiting or running jobs does not
resume it. Recovery and worker-error pauses still require attention and a manual
resume. A history-only selection or a keep-original request does not restart work.

The queue-size display totals the source sizes recorded when requests were
added. It includes waiting and running requests, not finished history. Unknown
sizes are shown separately. It does not measure current temporary storage or
predict how much space a conversion will save; a disconnected display labels
its previous queue totals as last known.
Cancellation uses `clear-queue-preview`, followed by `clear-queue-confirm` with
the returned `confirmation_id`; do not blindly repeat confirmation requests.

To remove just one waiting video, send `{"action":"remove-queued","id":"request-id"}`
to `/api/control`, using the request ID from `/api/controls`. This keeps its
history and files, and leaves other jobs and the queue's pause state alone.
If the worker has already started that request, removal is refused; refresh
the queue to see its current state. Repeating an already completed removal is safe.

## Network access

The current app has no login. Keep it on a trusted network and configure explicit
allowed hosts. The control token protects against cross-site writes; it is not
a password. Do not expose the app directly to the internet. For access outside
your trusted network, use an authenticated HTTPS gateway or VPN. Host checks,
media path restrictions and write confirmation apply to API requests too.
