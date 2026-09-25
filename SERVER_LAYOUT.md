# Server Layout — lab.bpm.in.tum.de

All files that make up the camera service on the lab server, grouped by location.

---

## Application code — `~/camera-service/`

| File | Function |
|---|---|
| `api/main.py` | FastAPI app. Defines all HTTP routes, lifespan startup/shutdown, error handling. |
| `api/cameras.py` | Camera abstraction. `MockCameraSource` for local dev; `UStreamerCameraSource` fetches JPEG frames from a µStreamer process over HTTP. |
| `api/captures.py` | Event capture logic. Saves one selected camera's JPEG per request with a `metadata.json` side-car. |
| `api/settings.py` | Config loader. Reads `production.yaml` (or `development.yaml` locally) via Pydantic and exposes a typed `Settings` object. |
| `dashboard/index.html` | Dashboard page served at `GET /dashboard` by FastAPI. |
| `dashboard/assets/styles.css` | Dashboard layout and Adwaita Mono font definition. Served at `GET /dashboard/assets/styles.css`. |
| `dashboard/assets/app.js` | Dashboard behavior, polling, and charts. Served at `GET /dashboard/assets/app.js`. |
| `dashboard/assets/fonts/adwaita-mono-regular.ttf` | Self-hosted font used throughout the dashboard. |
| `dashboard/assets/icons/download.svg` | Download icon for History captures. |
| `config/production.yaml` | **Active config** (gitignored). Contains real device paths, ports, storage, and `api.public_base_url` for public image links. |
| `.venv/` | Python virtual environment. All dependencies installed here via `pip`. |
| `requirements.txt` | Pinned Python dependencies (`fastapi`, `uvicorn`, `httpx`, `pydantic`, …). |

---

## Systemd service files — `/etc/systemd/system/`

| File | Function |
|---|---|
| `camera-capture@.service` | Parameterized unit for µStreamer. One instance per camera (`@whiteboard`, `@robot`). Reads device/port/resolution/FPS from the matching `.env` file in `/etc/camera-service/`. Starts on boot, restarts on crash. |
| `camera-api.service` | Unit for the FastAPI process (`uvicorn`). Depends on both capture units. Starts on boot, restarts on crash. |

---

## Camera environment configs — `/etc/camera-service/`

| File | Function |
|---|---|
| `whiteboard.env` | Variables for the whiteboard µStreamer instance: `DEVICE`, `PORT=8101`, `RESOLUTION=1280x720`, `FPS=30`. Read by `camera-capture@whiteboard.service`. |
| `robot.env` | Same for the robot camera: `DEVICE`, `PORT=8102`, `RESOLUTION=1280x720`, `FPS=30`. Read by `camera-capture@robot.service`. |

---

## Nginx config — `/etc/nginx/cpee.d/locations.d/`

| File | Function |
|---|---|
| `camera` | Location blocks inserted into the existing lab Nginx config. Routes `/cameras/…` requests: MJPEG stream endpoints go **directly to µStreamer** (lower latency); all other requests proxy to FastAPI. Handles TLS termination upstream. |

---

## Capture storage — `storage.captures_dir`

Created automatically by the app on startup. The production template uses
`/var/lib/camera-service/captures`; the path can be changed in the active config.

| Path | Content |
|---|---|
| `{event_id}/{camera_id}_YYYYMMDDTHHMMSSmmmZ.jpg` | One timestamped JPEG from the selected camera. |
| `{event_id}/metadata.json` | Capture timestamp, selected image URL, and any camera error. |

---

## Request flow

### Snapshot (`GET /cameras/api/v1/cameras/whiteboard/snapshot.jpg`)

```
Client
  │
  │  HTTPS  →  lab.bpm.in.tum.de:443
  ▼
Nginx                          /etc/nginx/cpee.d/locations.d/camera
  │  strips /cameras prefix
  │  proxy_pass → 127.0.0.1:8100
  ▼
FastAPI (uvicorn)              ~/camera-service/api/main.py
  │  get_snapshot()
  │  calls camera.snapshot()
  ▼
UStreamerCameraSource          ~/camera-service/api/cameras.py
  │  GET http://127.0.0.1:8101/?action=snapshot
  ▼
µStreamer                      systemd: camera-capture@whiteboard
  │  reads latest JPEG frame from USB device buffer
  ▼
/dev/v4l/by-id/usb-046d_Logitech_StreamCam_51EF0655-video-index0
  │  (whiteboard Logitech StreamCam, 1280×720 @ 30fps)
  │
  ◄── JPEG bytes bubble back up through the same chain ──►
```

**Total latency (measured):** ~45 ms TTFB from outside the network.

---

### MJPEG stream (`GET /cameras/api/v1/cameras/whiteboard/stream.mjpeg`)

```
Client
  │
  │  HTTPS  →  lab.bpm.in.tum.de:443
  ▼
Nginx                          /etc/nginx/cpee.d/locations.d/camera
  │  matched by exact location block
  │  proxy_pass → 127.0.0.1:8101/?action=stream   ← bypasses FastAPI
  │  proxy_buffering off
  ▼
µStreamer                      systemd: camera-capture@whiteboard
  │  streams multipart/x-mixed-replace MJPEG frames continuously
  ▼
/dev/v4l/by-id/usb-046d_Logitech_StreamCam_51EF0655-video-index0
```

FastAPI is **not involved** for streams. Nginx proxies directly to µStreamer.

**Total latency (measured):** ~28 ms TTFB from outside the network.

---

### Event capture (`POST /cameras/api/v1/cameras/whiteboard/captures`)

```
Client (CPEE or curl)
  │
  │  HTTPS POST (empty body)
  ▼
Nginx  →  FastAPI (port 8100)
  ▼
CaptureStore.capture()         ~/camera-service/api/captures.py
  │  requests one selected camera
  └──► µStreamer :8101  →  whiteboard JPEG
  │
  │  writes to configured captures_dir/{generated_event_id}/
  │    whiteboard_<UTC timestamp>.jpg
  │    metadata.json
  ▼
Client receives 201 + complete image URL in plain text and Location
```

To capture the robot, make a separate POST to
`/cameras/api/v1/cameras/robot/captures`. The server generates its ID.
`api.public_base_url` in production config supplies the external `/cameras`
prefix on the returned image URL.

---

## Process overview

```
boot
 │
 ├── camera-capture@whiteboard  →  µStreamer :8101  →  /dev/video* (whiteboard)
 ├── camera-capture@robot       →  µStreamer :8102  →  /dev/video* (robot)
 └── camera-api                 →  uvicorn  :8100   →  FastAPI app
                                                          │
Nginx :443  ──────────────────────────────────────────────┤
  /cameras/…/stream.mjpeg  →  µStreamer direct            │
  /cameras/…               →  FastAPI ────────────────────┘
```
