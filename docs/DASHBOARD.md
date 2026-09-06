# Local job dashboard

## Preserved control-room design

The user explicitly approved the control-room design in `python/ui/__init__.py` and
requested that it persist in the main repository. Keep its layout, visual
hierarchy, stationary completed-work bars, and text-only stage updates when
extending the product. The standalone monitor and Web UI history route share
this same template. Do not substitute the older job-card page during merges.
`tests/dashboard_ui_test.js` covers its DOM behavior; review visual changes
explicitly rather than treating them as incidental refactoring.

The dashboard now has a focused current-run panel, capability checks, sample
size/speed results, and searchable/filterable compact job history. Details and
logs open on demand. It uses only local Python/HTML/CSS/JavaScript, with no CDN
or added packages. Refresh an already-open page after updating the dashboard.

**No animated progress bars:** overall work uses a stationary bar based on
completed tests or inspected files. Stage changes do not reset it. Current-stage
progress is text only; unknown progress displays a message without a bar. The
overall test count is not a time estimate. Older logs without an overall count
show text for running-stage progress rather than a misleading whole-job bar.

New scans that reach the end with unreadable files show **Completed with errors**.
Validation success remains distinct from playback approval. Historical records
keep their original status. Unicode filenames are supported by shared CLI logging.

From the MuxMender project directory:

```powershell
python python/dashboard.py
```

Open http://127.0.0.1:8765. Keep this process running while monitoring;
Ctrl+C stops the dashboard, not an encode. No extra packages or VS Code required.
Use `--port 8766` if the default port is occupied. `--root PATH` selects a project
whose `reports` and `test-output` folders should be monitored.

New CLI runs of `muxmender.py`, `run_logged.py`, `dv_full_file.py`, and
`dv_preservation_test.py` automatically retain a unique job record and terminal
log under `reports/job-*`, whether or not the dashboard is open. Installed
`muxmender` and `muxmender-dashboard` commands provide the same behavior.
Programmatic calls to `main()` are not automatically logged.

Existing runs with `status.json` or `validation.json` are discovered without
restarting them. Existing `terminal.log` progress markers take precedence over
phase-start percentages. Legacy runs without logs may only show phase progress;
old unstructured logs alone are not imported. If a custom work directory is
outside the project, its new job log is still tracked but the dashboard does not
read that external directory. Multi-file scans are one job; the progress bar
represents the currently reported file/stage, not an aggregate batch ETA.

The browser refreshes every three seconds. ETA is **current-stage only** and is
an estimate. A quiet live process may be marked stale; this is not a failure
diagnosis. Job records survive server restarts. A dead unfinished process is
marked interrupted. Historical process IDs may be reused, so old records with
no recent activity are never treated as reliable live progress.

Validation success is not visual-quality approval. `awaiting-playback` remains
visible until playback review is recorded by a future workflow. Missing generated
outputs do not erase historical results. Source checks report size/mtime checks,
not full source hashes.

The server binds **127.0.0.1 only**, validates Host, serves no arbitrary files,
and exposes read-only job/log endpoints. It does not launch/stop jobs, scan
source drives, stream video, install dependencies, or delete/modify media.
Anyone using this PC can view the local logs, which may contain media paths.
Do not expose or reverse-proxy this development server onto a network.


NVIDIA execution reports separate encoding and finalization phases with the
same overall file count. Finalization copies original non-video tracks; it
does not re-encode the video. No animated or indeterminate bars were added.
