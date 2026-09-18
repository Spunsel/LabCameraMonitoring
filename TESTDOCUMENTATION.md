# Test Documentation

How to verify the camera service is working correctly on `lab.bpm.in.tum.de`.
All `curl` commands run on lab in an SSH terminal unless stated otherwise.

---

## Prerequisites

Both processes must be running before any test will work.

| Process | Command | Port |
|---|---|---|
| µStreamer | `ustreamer --device /dev/v4l/by-id/usb-046d_Logitech_StreamCam_DA702655-video-index0 --host 127.0.0.1 --port 8101 --format MJPEG --resolution 1280x720 --desired-fps 15` | 8101 |
| FastAPI | `CAMERA_SERVICE_CONFIG=config/production.yaml .venv/bin/uvicorn api.main:app --host 127.0.0.1 --port 8100` | 8100 |

After systemd is set up (Session 5) they start automatically — manual start will no longer be needed.

---

## T-01 · Process health check

**What it tests:** The FastAPI process is running and accepting requests.

```bash
curl http://127.0.0.1:8100/healthz
```

**Expected response:**
```json
{"status":"ok"}
```

**HTTP status:** `200`

---

## T-02 · Camera readiness check

**What it tests:** The camera is plugged in, µStreamer is running, and frames are being delivered.

```bash
curl http://127.0.0.1:8100/readyz
```

**Expected response (camera healthy):**
```json
{"ready": true, "cameras": {"whiteboard": true}}
```

**Expected response (camera unavailable):**
```json
{"ready": false, "cameras": {"whiteboard": false}}
```

**HTTP status:** `200` when ready, `503` when not.

---

## T-03 · Snapshot — response headers

**What it tests:** Correct `Content-Type`, `Cache-Control`, and custom camera headers are present.

```bash
curl -I http://127.0.0.1:8100/api/v1/cameras/whiteboard/snapshot.jpg
```

**Expected headers:**
```
HTTP/1.1 200 OK
content-type: image/jpeg
cache-control: no-store
x-camera-id: whiteboard
x-captured-at: 2026-09-18T14:30:12.420Z
```

---

## T-04 · Snapshot — file content

**What it tests:** The returned file is a real JPEG at the correct resolution.

```bash
curl http://127.0.0.1:8100/api/v1/cameras/whiteboard/snapshot.jpg -o /tmp/wb.jpg
ls -lh /tmp/wb.jpg
file /tmp/wb.jpg
```

**Expected output:**
```
-rw-r--r-- 1 lab lab 118K Sep 18 15:29 /tmp/wb.jpg
JPEG image data, baseline, precision 8, 1280x720, components 3
```

- File size should be **30–150 kB** for a real scene (near-zero means something is wrong).
- `components 3` means colour (RGB). `components 1` would mean greyscale.

**View the image on your local machine:**
```bash
# Run on your LOCAL machine
scp lab:/tmp/wb.jpg ~/Desktop/lab-snapshot.jpg
```

---

## T-05 · Camera list

**What it tests:** The camera inventory endpoint lists all configured cameras with correct metadata.

```bash
curl -s http://127.0.0.1:8100/api/v1/cameras | python3 -m json.tool
```

**Expected response:**
```json
{
  "whiteboard": {
    "id": "whiteboard",
    "available": true,
    "snapshot_url": "/api/v1/cameras/whiteboard/snapshot.jpg",
    "stream_url": "/api/v1/cameras/whiteboard/stream.mjpeg"
  }
}
```

---

## T-06 · Event capture — create

**What it tests:** Both cameras are captured simultaneously, images are saved to disk, and a JSON response with URLs is returned. This is the endpoint CPEE will call.

```bash
curl -s -X POST http://127.0.0.1:8100/api/v1/captures \
  -H "Content-Type: application/json" \
  -d '{"event_id": "test-001", "cameras": ["whiteboard"], "store": true}' \
  | python3 -m json.tool
```

**Expected response:**
```json
{
  "event_id": "test-001",
  "captured_at": "2026-09-18T14:30:12.420Z",
  "images": {
    "whiteboard": "/api/v1/captures/test-001/whiteboard.jpg"
  },
  "errors": {}
}
```

**HTTP status:** `201`

The image is saved on disk at:
```
/home/lab/camera-service/var/captures/test-001/whiteboard.jpg
```

---

## T-07 · Event capture — retrieve metadata

**What it tests:** Previously stored capture metadata can be read back by event ID.

```bash
curl -s http://127.0.0.1:8100/api/v1/captures/test-001 | python3 -m json.tool
```

**Expected response:** Same structure as T-06.
**HTTP status:** `200`. Returns `404` if the event ID was never captured.

---

## T-08 · Event capture — retrieve stored image

**What it tests:** The saved JPEG for a specific capture event can be downloaded by URL.

```bash
curl http://127.0.0.1:8100/api/v1/captures/test-001/whiteboard.jpg -o /tmp/captured.jpg
ls -lh /tmp/captured.jpg
file /tmp/captured.jpg
```

**Expected:** Same size and format as T-04. Copy to local machine with `scp` to view it.

---

## T-09 · Unknown camera → 404

**What it tests:** Requesting a camera that is not configured returns a clear error, not a crash.

```bash
curl -s http://127.0.0.1:8100/api/v1/cameras/robot/snapshot.jpg
```

**Expected response:**
```json
{"detail": "Unknown camera 'robot'"}
```

**HTTP status:** `404`

---

## T-10 · Unknown capture → 404

**What it tests:** Requesting metadata for a non-existent event ID returns a clear error.

```bash
curl -s http://127.0.0.1:8100/api/v1/captures/does-not-exist
```

**Expected response:**
```json
{"detail": "Capture 'does-not-exist' not found"}
```

**HTTP status:** `404`

---

## T-11 · Interactive API documentation

FastAPI generates interactive docs automatically. Useful for exploring all endpoints in a browser.

**On your local machine** — forward the port:
```bash
ssh -L 8100:127.0.0.1:8100 lab
```

Then open in a browser:
- **http://127.0.0.1:8100/docs** — Swagger UI (try every endpoint interactively)
- **http://127.0.0.1:8100/redoc** — ReDoc (clean reference view)

---

## Failure mode tests

These verify the service behaves correctly when something goes wrong.
Run them when the hardware or systemd setup is being validated.

| Test | How to trigger | Expected behaviour |
|---|---|---|
| µStreamer stopped | `Ctrl+C` on µStreamer terminal | `/readyz` returns `503 {"ready":false}` |
| Camera unplugged | Unplug USB cable | `/readyz` returns `503` within a few seconds |
| Camera reconnected | Plug USB cable back in | µStreamer reconnects automatically; `/readyz` returns `200` again |
| Lab server rebooted | `sudo reboot` | After Session 5 (systemd): both services restart automatically |
| Two concurrent snapshots | Run two `curl` commands simultaneously | Both return valid JPEGs; no conflict |

---

## Test results log

| Date | Test | Result | Notes |
|---|---|---|---|
| 2026-09-18 | T-01 | ✓ PASS | `{"status":"ok"}` |
| 2026-09-18 | T-02 | ✓ PASS | `{"ready":true,"cameras":{"whiteboard":true}}` |
| 2026-09-18 | T-04 | ✓ PASS | 118 kB JPEG, 1280×720, colour |
