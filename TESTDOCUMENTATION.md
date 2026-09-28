# Verification

Run automated checks from the project directory with development dependencies
installed:

```bash
.venv/bin/python -m pytest tests/test_captures.py
node tests/test_api_console.mjs
```

Python checks use temporary storage and a synthetic JPEG frame header. They
cover unique filenames, image dimensions, complete-pair listing, retention,
storage statistics, saved-image/metadata retrieval, removed-route rejection,
and the OpenAPI schema. No camera hardware or production storage is accessed.
Node checks use a DOM stand-in and mocked HTTP responses; they cover request
construction, prefix handling, curl quoting, response display, operator keys,
cancellation and duplicate-write prevention. They do not provide visual tests.

## Manual checks on lab

Run these commands over SSH. The capture POST below intentionally saves one
snapshot; the other requests read existing state. Set a local API base:

```bash
camera_api_base=http://127.0.0.1:8100
```

### Health, cameras and readiness

```bash
curl -fsS "$camera_api_base/healthz" | python3 -m json.tool
curl -fsS "$camera_api_base/api/v1/cameras" | python3 -m json.tool
curl -sS -i "$camera_api_base/readyz"
```

Health should return `200` and `status: ok`. Camera IDs should include whiteboard
and robot. Readiness returns `200` when all cameras respond, otherwise `503`.

### Immediate snapshot

```bash
curl -fsS -D - -o /tmp/camera-check.jpg \
  "$camera_api_base/api/v1/cameras/whiteboard/snapshot.jpg"
file /tmp/camera-check.jpg
```

Expect `200`, `Content-Type: image/jpeg`, `Cache-Control: no-store`, and camera
and timestamp headers. This request creates no saved capture on the server.
Check the image dimensions against the active camera resolution.

### Save and retrieve one snapshot

```bash
saved_url=$(curl -fsS -X POST \
  "$camera_api_base/api/v1/cameras/whiteboard/captures")
capture_filename=${saved_url##*/}
metadata_filename=${capture_filename%.jpg}.json
curl -fsS -D - -o /tmp/camera-saved-check.jpg \
  "$camera_api_base/api/v1/captures/$capture_filename"
curl -fsS "$camera_api_base/api/v1/captures/$metadata_filename" \
  | python3 -m json.tool
curl -fsS "$camera_api_base/api/v1/captures?limit=10" | python3 -m json.tool
curl -fsS "$camera_api_base/api/v1/captures/stats" | python3 -m json.tool
```

The bodyless POST returns `201`, with a complete JPEG URL as text and in the
`Location` header. Both GET requests return `200`. Metadata includes camera ID,
capture time, filename, size, dimensions and content type. The listing includes
the new filename and is sorted newest first. Storage statistics count top-level
JPEG/JSON files. Retention runs at startup and hourly, deleting pairs and orphaned
JPEGs older than 48 hours; subdirectories are ignored and left untouched.

### API specification and errors

```bash
curl -fsS "$camera_api_base/openapi.json" | python3 -m json.tool
curl -sS -o /dev/null -w '%{http_code}\n' \
  "$camera_api_base/api/v1/captures/missing.json"
curl -sS -o /dev/null -w '%{http_code}\n' \
  -H 'Content-Type: application/json' -d '{}' \
  "$camera_api_base/api/v1/cameras/whiteboard/captures"
```

The specification contains the current camera, capture, controls and monitoring
endpoints. The missing metadata request returns `404`; a capture POST containing
a body returns `400`.

## Dashboard checks

- Confirm tab order: Stream, Snapshots, History, Docs, API Console. Settings
  appears as an icon beside the theme toggle at every width. Narrow the browser
  and confirm the remaining page labels switch to icons without overlapping
  Settings or the theme toggle.
- Open API, select **Get API specification**, and execute. Expect a formatted
  JSON schema, `200`, response headers, and a curl URL ending in `/openapi.json`
  with the public `/cameras` prefix retained. Verify copy URL/curl/response.
- Confirm Operation and Camera selectors sit beside each other for camera
  requests; the schema request does not need a camera or operator key.
- Capture a snapshot and verify its History download and copy-link actions.
- Open both cameras' streams and check Settings without changing values.
