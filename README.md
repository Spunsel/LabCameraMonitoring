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
       └── Nginx (TLS + auth)   → https://lab.bpm.in.tum.de/cameras/
```

CPEE on demo/coruscant calls the HTTPS API to trigger captures or retrieve
snapshots. Image data never passes through demo.

---

## API endpoints

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/healthz` | Process health |
| `GET` | `/readyz` | Both cameras delivering frames |
| `GET` | `/api/v1/cameras` | List cameras and current state |
| `GET` | `/api/v1/cameras/{id}/snapshot.jpg` | Current JPEG snapshot |
| `GET` | `/api/v1/cameras/{id}/stream.mjpeg` | Live MJPEG stream |
| `POST` | `/api/v1/captures` | Capture one or both cameras (CPEE) |
| `GET` | `/api/v1/captures` | List stored capture event IDs (max 20) |
| `GET` | `/api/v1/captures/{event_id}` | Capture metadata |
| `GET` | `/api/v1/captures/{event_id}/{camera_id}.jpg` | Stored capture image |
| `GET` | `/api/v1/status` | Camera availability, resolution, fps, uptime |
| `GET` | `/dashboard` | Live monitoring dashboard |

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
committed) and fill in the real device paths.

```yaml
cameras:
  whiteboard:
    source: v4l2
    device: /dev/v4l/by-id/usb-046d_Logitech_StreamCam_SERIALX-video-index0
    width: 1280
    height: 720
    fps: 30
  robot:
    source: v4l2
    device: /dev/v4l/by-id/usb-046d_Logitech_StreamCam_SERIALY-video-index0
    width: 1280
    height: 720
    fps: 30

ustreamer:
  whiteboard_port: 8101
  robot_port: 8102

api:
  port: 8100

storage:
  captures_dir: var/captures   # relative to ~/camera-service/ — created automatically
```

---

## Deployment (lab.bpm.in.tum.de)

```bash
# 1. Install µStreamer (Fedora)
sudo dnf install ustreamer

# 2. Add lab user to video group
sudo usermod -aG video lab
# log out and back in

# 3. Sync code to the server (from local machine)
rsync-lab   # uses the alias defined in the "Updating" section below

# 4. Create Python venv and install dependencies (on server)
cd ~/camera-service
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# 5. Create production config from the template (on server)
cp config/production.example.yaml config/production.yaml
# Edit production.yaml: fill in real device paths from /dev/v4l/by-id/

# 6. Create camera environment files (on server, not in repo)
sudo mkdir -p /etc/camera-service

# whiteboard camera
sudo tee /etc/camera-service/whiteboard.env <<EOF
DEVICE=/dev/v4l/by-id/usb-046d_Logitech_StreamCam_51EF0655-video-index0
PORT=8101
RESOLUTION=1280x720
FPS=30
EOF

# robot camera
sudo tee /etc/camera-service/robot.env <<EOF
DEVICE=/dev/v4l/by-id/usb-046d_Logitech_StreamCam_DA702655-video-index0
PORT=8102
RESOLUTION=1280x720
FPS=30
EOF

# 7. (no action needed) Capture storage is created automatically at
#    ~/camera-service/var/captures/ when camera-api first starts.

# 8. Install and enable systemd units (on server)
sudo cp deployment/systemd/*.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now camera-capture@whiteboard
sudo systemctl enable --now camera-capture@robot
sudo systemctl enable --now camera-api

# 9. Configure Nginx (on server)
sudo cp deployment/nginx/camera-api.conf /etc/nginx/cpee.d/locations.d/camera
sudo nginx -t && sudo systemctl reload nginx
```

---

## Updating the service after `rsync`

Sync local changes to the server with the `rsync-lab` alias (set in `~/.bashrc`):

```bash
alias rsync-lab='rsync -av \
  --exclude=".git" --exclude=".venv" --exclude="var/" \
  --exclude=".pytest_cache" --exclude="test-captures" \
  --exclude="config/production.yaml" --exclude="LABSERVERCOMMANDS.md" \
  --exclude="ROADMAP.md" --exclude="TESTDOCUMENTATION.md" \
  ~/CameraMonitoring/ lab:~/camera-service/'
```

After running `rsync-lab`, SSH into the server and run only what changed:

| What changed | Commands on lab |
|---|---|
| `api/*.py` | `sudo systemctl restart camera-api` |
| `deployment/nginx/camera-api.conf` | `sudo cp ~/camera-service/deployment/nginx/camera-api.conf /etc/nginx/cpee.d/locations.d/camera && sudo nginx -t && sudo systemctl reload nginx` |
| `deployment/systemd/*.service` | `sudo cp ~/camera-service/deployment/systemd/*.service /etc/systemd/system/ && sudo systemctl daemon-reload && sudo systemctl restart camera-api camera-capture@whiteboard camera-capture@robot` |

After restarting FastAPI, verify it came back up:

```bash
sudo systemctl status camera-api
curl -s http://127.0.0.1:8100/healthz
```

---

## Project layout

```
camera-service/
├── api/
│   ├── main.py          # FastAPI app, routes, middleware
│   ├── cameras.py       # Camera abstraction (Mock / V4L2-via-µStreamer)
│   ├── captures.py      # Event capture logic and storage
│   ├── settings.py      # Pydantic-settings config loader
│   └── dashboard.py     # Self-contained HTML/CSS/JS for /dashboard
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


