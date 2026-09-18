# camera-service

Stable camera gateway for the BPM lab at TU München.
Provides on-demand JPEG snapshots, an MJPEG live stream, and a CPEE-friendly
event-capture endpoint for the **whiteboard** and **robot** Logitech StreamCams.

---

## Architecture

```
lab.bpm.in.tum.de
│
├── µStreamer @127.0.0.1:8101   ← whiteboard camera (/dev/v4l/by-id/…)
├── µStreamer @127.0.0.1:8102   ← robot camera     (/dev/v4l/by-id/…)
│
└── FastAPI @127.0.0.1:8100     ← unified API
       │
       └── Nginx (TLS + auth)   → https://lab.bpm.in.tum.de/camera-api/
```

CPEE on demo/coruscant calls the HTTPS API to trigger captures or retrieve
snapshots. Image data never passes through demo.

---

## API endpoints

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/api/v1/cameras` | List cameras and current state |
| `GET` | `/api/v1/cameras/{id}/snapshot.jpg` | Current JPEG snapshot |
| `GET` | `/api/v1/cameras/{id}/stream.mjpeg` | Live MJPEG stream |
| `POST` | `/api/v1/captures` | Capture one or both cameras |
| `GET` | `/api/v1/captures/{event_id}` | Capture metadata |
| `GET` | `/healthz` | Process health |
| `GET` | `/readyz` | Both cameras delivering frames |

### Snapshot response headers

```
Content-Type: image/jpeg
Cache-Control: no-store
X-Camera-Id: whiteboard
X-Captured-At: 2026-09-18T14:30:12.420Z
```

### Capture request (CPEE)

```json
{
  "event_id": "process-4711-activity-8",
  "cameras": ["whiteboard", "robot"],
  "store": true
}
```

### Capture response

```json
{
  "event_id": "process-4711-activity-8",
  "captured_at": "2026-09-18T14:30:12.420Z",
  "images": {
    "whiteboard": "/api/v1/captures/process-4711-activity-8/whiteboard.jpg",
    "robot":      "/api/v1/captures/process-4711-activity-8/robot.jpg"
  }
}
```

---

## Quick start (local development)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# use mock cameras – no physical hardware required
export CAMERA_SERVICE_CONFIG=config/development.yaml

uvicorn api.main:app --reload --host 127.0.0.1 --port 8100
```

Then:

```bash
curl http://127.0.0.1:8100/healthz
curl http://127.0.0.1:8100/api/v1/cameras
curl http://127.0.0.1:8100/api/v1/cameras/whiteboard/snapshot.jpg -o whiteboard.jpg
```

---

## Configuration

Copy `config/production.example.yaml` to `config/production.yaml` (not
committed) and fill in the real device paths and API token.

```yaml
cameras:
  whiteboard:
    source: v4l2
    device: /dev/v4l/by-id/usb-046d_Logitech_StreamCam_SERIALX-video-index0
    width: 1920
    height: 1080
    fps: 15
  robot:
    source: v4l2
    device: /dev/v4l/by-id/usb-046d_Logitech_StreamCam_SERIALY-video-index0
    width: 1920
    height: 1080
    fps: 15

ustreamer:
  whiteboard_port: 8101
  robot_port: 8102

api:
  port: 8100
  token: "REPLACE_ME"

storage:
  captures_dir: /var/lib/camera-service/captures
```

---

## Deployment (lab.bpm.in.tum.de)

```bash
# 1. Install µStreamer (Fedora)
sudo dnf install ustreamer

# 2. Add lab user to video group
sudo usermod -aG video lab
# log out and back in

# 3. Copy and enable systemd units
sudo cp deployment/systemd/*.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now camera-capture@whiteboard
sudo systemctl enable --now camera-capture@robot
sudo systemctl enable --now camera-api

# 4. Configure Nginx
sudo cp deployment/nginx/camera-api.conf /etc/nginx/conf.d/
sudo nginx -t && sudo systemctl reload nginx
```

---

## Project layout

```
camera-service/
├── api/
│   ├── main.py          # FastAPI app, routes, middleware
│   ├── cameras.py       # Camera abstraction (Mock / V4L2-via-µStreamer)
│   ├── captures.py      # Event capture logic and storage
│   └── settings.py      # Pydantic-settings config loader
├── config/
│   ├── development.yaml          # Mock cameras – safe to commit
│   └── production.example.yaml  # Template – commit; real file gitignored
├── deployment/
│   ├── systemd/
│   │   ├── camera-capture@.service
│   │   └── camera-api.service
│   └── nginx/
│       └── camera-api.conf
├── tests/
│   ├── fixtures/
│   │   ├── whiteboard.jpg
│   │   └── robot.jpg
│   ├── conftest.py
│   ├── test_api.py
│   └── test_cameras.py
├── requirements.txt
├── pyproject.toml
└── README.md
```

---

## Rollout sequence

1. Local: implement mock cameras → snapshot + health endpoints.
2. Lab (early): deploy one-camera minimal version bound to localhost.
3. Lab: connect second camera, validate by-id paths.
4. Lab: add event capture and CPEE integration test.
5. Lab: configure HTTPS reverse proxy and API token.
6. Lab: systemd + reboot / unplug / concurrency tests.
7. Retire old ngrok endpoints.
8. (Later) Fedora upgrade in a separate maintenance window.
