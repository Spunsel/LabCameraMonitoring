# Test Documentation

How to verify the camera service is working correctly on `lab.bpm.in.tum.de`.
All `curl` commands run on lab in an SSH terminal unless stated otherwise.

---

## Prerequisites

Both processes must be running before any test will work.
Since systemd is configured (Step 5), they start automatically on boot — **no manual start needed.**

| Process | Systemd unit | Port |
|---|---|---|
| µStreamer (whiteboard) | `camera-capture@whiteboard` | 8101 |
| µStreamer (robot) | `camera-capture@robot` | 8102 |
| FastAPI | `camera-api` | 8100 |

Check status:
```bash
systemctl status camera-capture@whiteboard camera-capture@robot camera-api
```

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
{"ready": true, "cameras": {"whiteboard": true, "robot": true}}
```

**Expected response (one camera unavailable):**
```json
{"ready": false, "cameras": {"whiteboard": true, "robot": false}}
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
  },
  "robot": {
    "id": "robot",
    "available": true,
    "snapshot_url": "/api/v1/cameras/robot/snapshot.jpg",
    "stream_url": "/api/v1/cameras/robot/stream.mjpeg"
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
curl -s http://127.0.0.1:8100/api/v1/cameras/nonexistent/snapshot.jpg
```

**Expected response:**
```json
{"detail": "Unknown camera 'nonexistent'"}
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

## T-12 · Capture list with metadata

**What it tests:** `GET /api/v1/captures` returns rich metadata (event_id, timestamp, file sizes) sorted by most recent first.

```bash
curl -s http://127.0.0.1:8100/api/v1/captures | python3 -m json.tool
# With explicit limit:
curl -s "http://127.0.0.1:8100/api/v1/captures?limit=5" | python3 -m json.tool
```

**Expected response:**
```json
[
  {
    "event_id": "test-001",
    "captured_at": "2026-09-24T09:47:00.123+00:00",
    "images": {
      "whiteboard": 165432,
      "robot": 99210
    }
  }
]
```

- `images` values are file sizes in bytes.
- Sorted by mtime (most recently created first).
- `?limit` accepts 1–50; default 10.

---

## T-13 · Camera status

**What it tests:** The status endpoint returns availability, resolution, fps, and API uptime for all cameras.

```bash
curl -s http://127.0.0.1:8100/api/v1/status | python3 -m json.tool
```

**Expected response:**
```json
{
  "uptime_seconds": 3742,
  "cameras": {
    "whiteboard": {
      "available": true,
      "resolution": "1280x720",
      "fps": 30
    },
    "robot": {
      "available": true,
      "resolution": "1280x720",
      "fps": 30
    }
  }
}
```

---

## T-14 · Monitoring dashboard

**What it tests:** The dashboard is served and returns valid HTML.

```bash
curl -s http://127.0.0.1:8100/dashboard | grep -c '<canvas'
# Expected: 2  (one canvas per camera)
```

Open in a browser via SSH port forward to view the full dashboard:
```bash
# Local machine:
ssh -L 8100:127.0.0.1:8100 lab
# Then open: http://127.0.0.1:8100/dashboard
```

The dashboard loads live MJPEG streams, measures snapshot latency every 5 s, and polls captures every 15 s.

---

## T-15 · Snapshot latency — manual measurement

**What it tests:** End-to-end snapshot latency from server side, for comparison with the dashboard readout.

```bash
# Floor: µStreamer direct (no FastAPI, no Nginx)
for cam in whiteboard robot; do
  port=$([[ $cam == whiteboard ]] && echo 8101 || echo 8102)
  printf "%-12s µStreamer direct:  " "$cam"
  for i in $(seq 10); do
    curl -s -o /dev/null -w "%{time_starttransfer}\n" \
      "http://127.0.0.1:${port}/?action=snapshot"
  done | awk '{s+=$1;n++} END{printf "avg TTFB %4.0fms\n", s/n*1000}'
done

# Full path: through FastAPI (same as dashboard measures, minus network)
for cam in whiteboard robot; do
  printf "%-12s FastAPI direct:    " "$cam"
  for i in $(seq 10); do
    curl -s -o /dev/null -w "%{time_starttransfer}\n" \
      "http://127.0.0.1:8100/api/v1/cameras/${cam}/snapshot.jpg"
  done | awk '{s+=$1;n++} END{printf "avg TTFB %4.0fms\n", s/n*1000}'
done
```

**Typical values:**
- µStreamer direct: ~3–8 ms (localhost HTTP only)
- FastAPI direct: ~15–20 ms (+ Python/uvicorn overhead)
- Dashboard reads: ~30–45 ms (+ real network + Nginx + TLS)

---

## T-16 · Real POST capture latency

**What it tests:** How long CPEE actually waits when triggering a capture (both cameras, with and without disk write).

```bash
# Without disk write (pure camera fetch, both cameras concurrent)
curl -s -o /dev/null \
  -w "TTFB %{time_starttransfer}s  total %{time_total}s\n" \
  -X POST http://127.0.0.1:8100/api/v1/captures \
  -H "Content-Type: application/json" \
  -d '{"event_id": "_probe_", "store": false}'

# With disk write (realistic CPEE scenario)
curl -s -o /dev/null \
  -w "TTFB %{time_starttransfer}s  total %{time_total}s\n" \
  -X POST http://127.0.0.1:8100/api/v1/captures \
  -H "Content-Type: application/json" \
  -d '{"event_id": "_probe_disk_"}'
```

**Typical values (server-side):** 15–25 ms TTFB. Disk write adds ~2–5 ms on SSD.

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
| 2026-09-18 | T-04 | ✓ PASS | 118 kB JPEG, 1280×720, colour — lab bench image confirmed correct |
