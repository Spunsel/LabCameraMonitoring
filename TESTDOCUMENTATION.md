# Verification

Reviewed against the packaged source on **2026-09-28**. Current automated suites
are listed below; the old `test_api.py`, `test_cameras.py` and `conftest.py` from
the initial scaffold are not present in this package.

## Automated checks

Run from the `CameraMonitoring` directory after installing `requirements.txt`
in a local environment. Node is needed for JavaScript tests; no npm installation
or frontend build is required.

```bash
.venv/bin/python -m pytest -q
node tests/test_api_calls.mjs
node tests/test_api_console.mjs
node tests/test_controls_ui.mjs
node tests/test_capture_mode_ui.mjs
bash -n deployment/setup-controls.sh
bash -n deployment/setup-capture-mode.sh
```

| Suite | Scope |
| --- | --- |
| `tests/test_captures.py` | Flat pairs, metadata/dimensions, collision handling, retention, statistics, capture routes and schema |
| `tests/test_controls.py` | V4L2 fixture parsing, access checks, ranges, modes, readback, reset and device errors |
| `tests/test_camera_configs.py` | Persistent named configurations, load ordering, one-step undo, stale and partial-change cases |
| `tests/test_capture_modes.py` | Mode discovery, validated helper transactions, mode persistence/rollback and settings restoration |
| `tests/test_activity.py` | Authorization, bounded/incremental history, restart, exclusions, privacy, errors and unchanged response chunks |
| `tests/test_api_console.mjs` | Request construction, curl quoting, response display, keys, cancellation and duplicate-write prevention |
| `tests/test_controls_ui.mjs` | Settings controls/access, save/discard, load/abort, undo and preview lifecycle |
| `tests/test_capture_mode_ui.mjs` | Staged mode selection, confirmation, access/busy state and reconnection |
| `tests/test_api_calls.mjs` | Incremental rows, limits, safe text rendering, restart reset, hidden-page polling and navigation |

The API CALLS implementation was checked on 2026-09-28: **82 backend tests and
all four JavaScript suites passed**. That is a recorded result, not a guarantee
that any future dependency installation has been tested. Python tests use fake
camera/subprocess responses and temporary storage. Node tests use DOM stand-ins
and mocked HTTP responses. They do not establish physical-camera behavior or
visual browser layout. No automated live-lab test is claimed.

A separate full-app mock-camera check confirmed a saved capture appears in API
activity with its filename. A local synthetic ASGI benchmark measured about
11 microseconds of added recording time per request (five runs of 10,000 1 KB
responses). It excludes camera/network time and is not a stream-FPS benchmark.

## Read-only checks on lab

```bash
camera_api_base=http://127.0.0.1:8100
curl -fsS "$camera_api_base/healthz" | python3 -m json.tool
curl -sS -i "$camera_api_base/readyz"
curl -fsS "$camera_api_base/api/v1/cameras" | python3 -m json.tool
curl -fsS "$camera_api_base/api/v1/status" | python3 -m json.tool
curl -fsS "$camera_api_base/api/v1/stream-metrics" | python3 -m json.tool
```

Health returns 200 and `status: ok`. Readiness returns 200 if all source
availability checks pass, otherwise 503. For physical cameras these are HTTP
ping checks; they do not prove that fresh frames are arriving. For a complete
check, inspect an actual JPEG and µStreamer's online state as well.

```bash
curl -fsS -D - -o /tmp/camera-check.jpg \
  "$camera_api_base/api/v1/cameras/whiteboard/snapshot.jpg"
file /tmp/camera-check.jpg
curl -fsS http://127.0.0.1:8101/state | python3 -m json.tool
```

Expect a JPEG response, `Cache-Control: no-store`, `X-Camera-Id` and an API-side
`X-Captured-At` timestamp. The local output file is downloaded by curl; the API
creates no retained capture for this GET. Repeat for robot/8102. Compare JPEG
dimensions with current mode, not with a fixed example resolution.

## Save and retrieve one capture

This check intentionally saves one image on the server:

```bash
saved_url=$(curl -fsS -X POST \
  "$camera_api_base/api/v1/cameras/whiteboard/captures")
capture_filename=${saved_url##*/}
metadata_filename=${capture_filename%.jpg}.json
curl -fsS -D - -o /tmp/camera-saved-check.jpg \
  "$camera_api_base/api/v1/captures/$capture_filename"
curl -fsS "$camera_api_base/api/v1/captures/$metadata_filename" | python3 -m json.tool
curl -fsS "$camera_api_base/api/v1/captures?limit=10" | python3 -m json.tool
curl -fsS "$camera_api_base/api/v1/captures/stats" | python3 -m json.tool
```

The bodyless POST returns 201, with the JPEG URL in text and `Location`. Both
GETs return 200. Metadata includes filename, camera, time, size, dimensions and
content type. The listing is newest first by filename timestamp. Stats are
whole-directory top-level JPG/JSON byte totals, not just the listing's totals.
Do not delete production captures to test retention; the automated tests use
temporary files for that behavior.

## API schema and controlled errors

```bash
curl -fsS "$camera_api_base/openapi.json" | python3 -m json.tool
curl -sS -o /dev/null -w '%{http_code}\n' "$camera_api_base/api/v1/captures/missing.json"
curl -sS -o /dev/null -w '%{http_code}\n' \
  -H 'Content-Type: application/json' -d '{}' \
  "$camera_api_base/api/v1/cameras/whiteboard/captures"
```

Expect 404 for missing metadata and 400 for a capture POST with a body. The
specification includes controls/configs/undo, capture mode and activity as well
as the core camera routes.

## API CALLS checks

```bash
read -rsp 'Operator key: ' CAMERA_CONTROLS_KEY
printf '\n'
curl -fsS -H "X-Camera-Control-Key: $CAMERA_CONTROLS_KEY" \
  "$camera_api_base/api/v1/activity" | python3 -m json.tool
unset CAMERA_CONTROLS_KEY
```

1. Open `#api-calls`, unlock, and confirm recent manual requests appear. A saved
   capture should link to its image. Failed requests should have red status text.
2. Change rows to 25/50/100. Confirm there are no pause controls or filters.
3. Expand an endpoint and inspect the full timestamp and request ID. Check that
   copied/displayed data contains no key, cookie, body or query string.
4. Use browser network tools to check incremental `after`/`session` polling.
   Leaving API CALLS or hiding the browser tab should stop that page's polling;
   other dashboard polling can still run.
5. Lock and confirm rows/key are cleared. Invalid credentials should not expose
   history. With no server key configured, access returns 503 rather than 403.
6. Check that successful tagged background polls, streams and activity requests
   do not populate the table. Failed background requests should remain visible.
7. During an otherwise planned API restart, confirm history resets and the page
   automatically accepts the new session. Restarting solely for this test is
   unnecessary if the automated reset checks are sufficient.

## Settings and capture-mode checks

Use a controlled lab session; image-control and mode writes affect all viewers.
Save the desired image configuration first. Follow
[CAMERA_CONTROLS.md](CAMERA_CONTROLS.md) and [CAPTURE_MODE.md](CAPTURE_MODE.md):

- Verify read-only mode, unlocking and locking both camera panels.
- Test one image change, one-step undo, save/discard and load/switch/abort.
- Pan/tilt need enough zoom to have a visible effect on these cameras.
- Distinguish driver defaults from a saved configuration; reset is not a factory
  reset. Auto-controlled numerical values need not equal manual defaults.
- After capture-mode setup, stage a supported resolution/FPS pair. Cancelling
  confirmation must not restart the camera; applying interrupts one camera.
- Verify readback, new JPEG dimensions, preview recovery and restored image
  settings. Reapply the original mode separately: image-control undo/configs do
  not restore capture mode.
- If a proxy/browser request times out, refresh current mode before retrying:
  the server-side transaction may still complete.

## Visual and performance checks

- Navigation is Stream, Snapshots, History, Docs, API Console, API CALLS; Settings
  stays icon-only beside theme. Check wide/narrow layouts and both themes.
- Verify `#api-console`, `#api-calls` and the compatibility `#api` link.
- Confirm API Console's run button is inside the endpoint box, copy buttons
  overlay the code boxes, and stacked cards scroll with the page.
- Confirm History download/copy actions and responsive per-camera tables.
- Confirm settings previews/names/refresh sit outside the image-control cards.
- Check API CALLS horizontal table scrolling and readable focus/status indicators.
- Compare snapshot request timings before/after deployment and with API CALLS
  open/closed. Observe stream metrics too. Use equivalent conditions and successful
  responses; the browser display FPS and true visual latency are not measured by
  the existing server metrics. See [USAGE.md](USAGE.md).
