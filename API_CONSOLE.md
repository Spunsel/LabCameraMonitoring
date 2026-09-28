# Interactive API Console

Reviewed against the packaged source on **2026-09-28**.
Open **API Console** at `dashboard#api-console`; `#api` remains a compatibility
alias. Select an operation and, when applicable, a camera. Editing fields builds
the request URL and a Bash curl command; nothing runs until the play button is
clicked. The button sends an HTTP request, not a shell command.

## Available operations

| Operation | Method and path |
| --- | --- |
| Get snapshot image | `GET /api/v1/cameras/{camera_id}/snapshot.jpg` |
| Save snapshot on server | `POST /api/v1/cameras/{camera_id}/captures` |
| List saved captures | `GET /api/v1/captures?limit=N` |
| Get saved image | `GET /api/v1/captures/{stem}.jpg` |
| Get capture metadata | `GET /api/v1/captures/{stem}.json` |
| Read camera settings | `GET /api/v1/cameras/{camera_id}/controls` |
| Change camera settings | `PATCH /api/v1/cameras/{camera_id}/controls` |
| Restore camera defaults | `POST /api/v1/cameras/{camera_id}/controls/reset` |
| Check operator key | `GET /api/v1/cameras/{camera_id}/controls/access` |
| List cameras | `GET /api/v1/cameras` |
| Get service status | `GET /api/v1/status` |
| Get stream metrics | `GET /api/v1/stream-metrics` |
| Get capture storage statistics | `GET /api/v1/captures/stats` |
| Check API health | `GET /healthz` |
| Get API specification | `GET /openapi.json` |
| Check camera readiness | `GET /readyz` |

The operation selector does not expose every API endpoint. Saved configurations,
undo and capture-mode APIs exist but are operated from Settings; recent request
history is on [API CALLS](API_CALLS.md). Continuous MJPEG playback is on Stream.
The full endpoint catalog is in [README.md](README.md).

Snapshot GET returns a frame from the running source, without retaining it on
the API. Saved capture POST has no request body and returns a 201 plain-text URL
and `Location`. Captures become eligible for cleanup after 48 hours; actual
removal happens at a successful cleanup. Readiness is a source availability
check, not a guarantee of fresh usable frames. Status FPS is the live target;
stream metrics supply a separate observed FPS estimate.

## Request and response interface

Operation and Camera selectors share a row for camera-specific requests. The
run button sits in the endpoint box. Copy buttons overlay the URL, curl and
response boxes; successful copies briefly show a tick. Wide screens show two
cards side by side; stacked cards grow with their content and use page scrolling.
The JSON response code box keeps its 15-line height limit and can scroll.

The response area shows the executed method/URL, HTTP status, elapsed browser
request time through body download, body size, available response headers and a
formatted JSON/text response or JPEG preview. The elapsed time is one total,
not separate TTFB and download-only measurements. It differs from API CALLS'
server-side duration. Saved-capture responses expose an image link. JPEGs can
be downloaded; text and JSON can be copied.

Code highlighting uses text nodes; response text is not executed as HTML.
Malformed JSON is shown as plain text. HTTP error bodies remain visible. The
executed URL remains visible even after fields change.

## Access and write behavior

Within the current operation list, settings PATCH, reset and key-check requests
need the shared operator key. The password field is separate from Settings and
API CALLS. It stays in page memory; **clear key**, reload or page exit clears it.
Switching dashboard tabs alone does not clear it. The other offered operations,
including saving a snapshot, do not send the operator key.

Generated curl commands prompt for the operator key in Bash rather than embedding
it. Browser requests reuse website authentication. Copied commands do not include
website credentials; supply those separately if required by Nginx.

PATCH uses native V4L2 integers:

```json
{"values":{"focus_automatic_continuous":0,"focus_absolute":30}}
```

Exposure is in 0.1 ms units; pan/tilt use arcseconds (3600 per degree). Read the
camera settings first for limits, menus and auto/manual dependencies. Reset asks
for confirmation and applies eligible **driver-reported image-control defaults**;
it does not restore a previous custom setup or reset resolution/FPS. The console
operation is still labelled “Restore camera defaults”; the Settings footer uses
“restore defaults.”

Writes affect all viewers. Cancellation and the 60-second timeout stop the
browser waiting; they cannot undo changes already applied. Check readback before
retrying a timed-out write. See [CAMERA_CONTROLS.md](CAMERA_CONTROLS.md).

## Deployment and checks

For a backend/frontend feature update, deploy matching API and dashboard files,
restart `camera-api.service` if Python files changed, then hard-refresh the
browser. Markdown-only changes require neither action. There are no new Python
dependencies for this console.

Run `node tests/test_api_console.mjs` for request construction, shell quoting,
validation and response handling. It uses a DOM stand-in and mocked responses,
not physical cameras or visual browser rendering. See
[TESTDOCUMENTATION.md](TESTDOCUMENTATION.md) for full checks.
