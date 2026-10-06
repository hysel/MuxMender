# The app API

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
Cancellation uses `clear-queue-preview`, followed by `clear-queue-confirm` with
the returned `confirmation_id`; do not blindly repeat confirmation requests.

## Network access

The current app has no login. Keep it on a trusted network and configure explicit
allowed hosts. The control token protects against cross-site writes; it is not
a password. Do not expose the app directly to the internet. For access outside
your trusted network, use an authenticated HTTPS gateway or VPN. Host checks,
media path restrictions and write confirmation apply to API requests too.
