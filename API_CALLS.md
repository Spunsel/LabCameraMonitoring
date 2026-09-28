# Recent API calls

Reviewed against the packaged source on **2026-09-28**.

Open **API CALLS** (`dashboard#api-calls`) and enter the existing operator key. The API
Console now uses `dashboard#api-console`; old `#api` bookmarks still open the console.
No new dependencies or server permissions are needed when the shared operator key is
already configured. Without it, protected activity requests return 503. See
[CAMERA_CONTROLS.md](CAMERA_CONTROLS.md) for shared-key setup.

The table shows time, method, endpoint, HTTP status, server-side duration and result.
Saved captures link to their JPEG; the link stops working after that capture is deleted
or its file pair becomes invalid. Expiry alone does not immediately block retrieval;
cleanup runs at startup and hourly. Expand an endpoint to see the full timestamp and
request ID. Times display in the browser's local timezone. Rows are ordered by
completion, newest first; the time column is when each request arrived.

Choose 25, 50 or 100 rows. Updates run every five seconds after the previous request
completes, only while this page and browser tab are visible. There are no pause controls
or filters. The key is kept only in browser memory; Lock, page reload or page exit
clears the key and displayed activity. API Calls has its own unlock, separate from
Settings and API Console.

## Recorded activity

Eligible paths are `/api/v1/…`, `/healthz`, `/readyz` and `/openapi.json`. The dashboard
HTML and generated documentation pages are not activity entries.

A bounded in-memory deque retains the latest 500 finite API requests across all clients.
It resets when the API restarts. This requires the existing **one API worker**
deployment; multiple workers would each have independent histories. This is a
recent-activity view, not a persistent audit log.

Successful GET requests explicitly marked `X-Camera-Background: 1` are omitted. The
dashboard marks its automatic status, stream-metric, capture-list, storage-statistic and
snapshot-preview polls. Failed background requests are kept. Manually run console
requests are not marked and remain visible. The background marker is a display
convention, not proof of client identity.

Static files, continuous MJPEG streams and `/api/v1/activity` (including failed access
attempts to that endpoint) are always excluded. Only requests reaching the API are
observable; requests rejected by the reverse proxy or sent directly to µStreamer are not
included.

No request/response bodies, query strings, cookies, operator keys or arbitrary headers
are stored. Unmatched paths are shown as `/api/v1/[unmatched]`. Errors use safe
status-based summaries instead of arbitrary exception text. Capture endpoints explicitly
attach the saved filename as request metadata. `X-Request-ID` normally links an eligible
response to its table row. An unhandled error response created outside the recorder may
not carry the header; the recorded row still has a generated ID. Request IDs are not
automatically added to all journal/access-log lines.

Duration uses a monotonic clock, from arrival at the middleware until the last response
body message is sent to the ASGI server. It can include server-side backpressure; it is
not the browser's download time, TTFB or camera latency. The middleware forwards body
chunks unchanged and does not buffer them.

## Activity endpoint

`GET /api/v1/activity` requires `X-Camera-Control-Key` on every request and returns
`Cache-Control: no-store` on successful responses. Parameters:

- `after`: last received numeric cursor (default 0).
- `session`: session ID returned by the previous response.
- `limit`: 1–500 records (default 100).

Response: `session_id`, `started_at`, `cursor`, `reset`, and `records`. An
absent/changed session or a cursor outside the retained range returns `reset: true`. The
client replaces its rows after a reset and otherwise merges new IDs. Each response
returns the newest records up to its limit and advances to the latest cursor. At most
100 rows are cached by the dashboard. In-flight requests do not appear until complete or
interrupted. More than 100 new records between polls can skip older rows because the
dashboard requests only the newest 100; it does not offer paging through the full
500-record buffer.

## Deployment

When installing the API CALLS feature, copy its matching API and dashboard files,
including `api/activity.py` and `dashboard/assets/api-calls.js`, then run:

```bash
sudo systemctl restart camera-api.service
```

Hard-refresh the dashboard after frontend changes. A Markdown-only update requires no
restart or refresh. Existing personal camera configurations are not changed by this
feature. The `.js.text` copies are supplied in `JavaScript-text/`.

## Validation and practical limits

From the project directory with its environment active, run:

```bash
python -m pytest -q
node tests/test_api_calls.mjs
node tests/test_api_console.mjs
node tests/test_controls_ui.mjs
```

Validated authentication, privacy exclusions, failures, bounded retention, incremental
polling, restart reset, hidden-page behavior, safe text rendering, unchanged body chunks
and a full-app capture/history request with mock cameras.

A local synthetic test (five runs of 10,000 one-kilobyte ASGI responses) measured
approximately 11 microseconds of added recording time per request. This excludes network
and physical cameras and is not a live-camera performance guarantee. Browser layout
rendering and physical-camera FPS/latency were not verified here. On the lab server,
compare snapshot timings and stream metrics before and after deployment, including while
API Calls is open.

See [TESTDOCUMENTATION.md](TESTDOCUMENTATION.md) for all current suites and lab checks.
