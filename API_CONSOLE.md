# Interactive API console

Open the API tab to select an operation and, where applicable, a camera. The
console builds the request URL and a Bash curl command as you edit the fields.
No request runs until you click the play icon in the endpoint box. Live MJPEG playback remains
on the Stream tab; the console handles finite image, JSON and text responses.

Supported operations include current snapshots, saved captures and metadata,
capture listings/storage, camera settings (read, change, reset, access check),
camera listings, service status, stream metrics, health, readiness and the
OpenAPI specification (`GET /openapi.json`). Select **Get API specification**
to inspect the current schema and copy the request URL, curl command or JSON.

Copy icons overlay the top-right of the URL, curl command and response boxes,
using the History copy-button style. Successful copies briefly show a tick.
The play button submits the selected HTTP request; it does not run a shell.

The response panel shows the executed method/URL, HTTP status, elapsed request
and download time, body size, response headers available to the browser, and
formatted JSON, plain text or a JPEG preview. Curl commands and valid JSON
responses use the same syntax colors as Docs in both themes. Highlighting uses
text nodes and spans; copied commands and responses remain plain text. Invalid
JSON and non-JSON responses stay plain text. HTTP error bodies remain visible.
Saved-capture responses expose the returned image URL. JPEG responses can be
downloaded; text/JSON responses can be copied. Responses are rendered as text,
never executed as HTML. The response URL identifies the request even if the
request fields have since changed.

Settings writes and key checks require an operator key. Enter it in the console's
password field; it is separate from the Settings page unlock and is kept only
in memory for this page session. Clear key removes it. Read-only requests and
snapshot capture requests do not send the key. Copied curl commands prompt for
the key in Bash instead of embedding it. Browser requests reuse the existing website login. The console does not add
HTTP Basic credentials to copied commands. If your external client needs them,
supply them separately from the camera operator key. Operation and Camera
selectors appear side by side for camera-specific requests.

PATCH bodies use native API integers, not display units: exposure is in 0.1 ms,
and pan/tilt are in arcseconds. Read camera settings first to inspect ranges,
menus and automatic/manual dependencies. Reset requires confirmation. Writes
affect all viewers. Cancel and the 60-second timeout stop waiting in the browser;
they do not undo work that the server may already have performed.

Navigation order is Stream, Snapshots, History, Docs, API Console. Settings is
always an icon beside the theme toggle. The header remains a single row; page
labels switch to icons on narrow screens. The active link uses aria-current.

## Deployment and checks

Deploy the updated API and dashboard files, restart `camera-api.service`,
then hard-refresh the dashboard. No new Python dependencies are required.
Capture retrieval uses the saved filename with `.jpg` or `.json`. Capture
subdirectories are ignored by listing, storage statistics and cleanup.

Run `node tests/test_api_console.mjs` for request construction, shell quoting,
validation and response handling tests. The test uses a DOM stand-in and mocked
HTTP responses. It does not execute commands against cameras or provide visual
browser coverage.
