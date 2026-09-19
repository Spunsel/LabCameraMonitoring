# Project Roadmap

Camera monitoring service for the BPM Lab at TU München.
Tracks every milestone from initial scaffold to full production deployment.

---

## Legend

| Symbol | Meaning |
|---|---|
| ✅ | Completed |

---

## Step 1 — Local scaffold and mock camera API ✅

**Goal:** Build and test the complete API locally without any physical hardware.

- [x] Created project structure (`api/`, `config/`, `deployment/`, `tests/`)
- [x] `api/settings.py` — YAML config loader (Pydantic-settings)
- [x] `api/cameras.py` — Camera abstraction: `MockCameraSource` and `UStreamerCameraSource`
- [x] `api/captures.py` — Event capture logic and disk storage
- [x] `api/main.py` — FastAPI app with all endpoints
- [x] `config/development.yaml` — mock camera config (safe to commit)
- [x] `config/production.example.yaml` — template for real lab config
- [x] `deployment/systemd/` — systemd unit files
- [x] `deployment/nginx/` — Nginx reverse proxy config
- [x] `tests/` — 20 automated tests (all green)
- [x] Git repository initialised

**Verified:** `pytest` → 20/20 passed. `curl /healthz` → `{"status":"ok"}`. Snapshot served from mock fixture.

---

## Step 2 — Hardware inspection on lab.bpm.in.tum.de ✅

**Goal:** Understand what is physically connected and what needs fixing before deployment.

- [x] SSH into `lab.bpm.in.tum.de`
- [x] `lsusb` — one StreamCam found: `046d:0893`, serial `DA702655`
- [x] `lsusb -t` — camera on **USB 2.0 (480M)** via VIA Labs hubs → max reliable resolution 1280×720
- [x] `ls -l /dev/v4l/by-id/` — stable device path confirmed: `usb-046d_Logitech_StreamCam_DA702655-video-index0`
- [x] `v4l2-ctl --list-devices` → `Permission denied` (video group missing)
- [x] `groups` → `lab wheel dialout` (no `video`)

**Finding:** One camera connected. Permissions need fixing. USB 2.0 limits resolution to 1280×720.

---

## Step 3 — Fix camera permissions on lab ✅

**Goal:** Allow the `lab` user to open `/dev/video*` devices.

- [x] `sudo usermod -aG video lab`
- [x] Log out and back in
- [x] `groups` → `lab wheel dialout video` ✓
- [x] `v4l2-ctl --list-devices` → StreamCam listed without error ✓

---

## Step 4 — Deploy code and confirm first real snapshot ✅

**Goal:** Get a real JPEG frame from the physical camera through the full API stack.

- [x] `rsync` project files to `~/camera-service/` on lab
- [x] `sudo dnf install -y ustreamer` (µStreamer 6.12)
- [x] `python3 -m venv .venv` + pip install all deps
- [x] `config/production.yaml` written with whiteboard camera (1280×720, USB by-id path)
- [x] µStreamer started: `--resolution 1280x720 --format MJPEG --desired-fps 15`
- [x] FastAPI started: `uvicorn api.main:app --host 127.0.0.1 --port 8100`
- [x] `GET /healthz` → `{"status":"ok"}` ✓
- [x] `GET /readyz` → `{"ready":true}` ✓
- [x] Snapshot: **118 kB JPEG, 1280×720, colour** ✓
- [x] Image visually confirmed — real lab bench photo ✓

**Note:** `--resolution WxH` is the correct µStreamer flag (not `--width`/`--height`).

---

## Step 5 — systemd: automatic startup and crash recovery ✅

**Goal:** Both processes start on boot and restart automatically after any crash. The service no longer depends on an open SSH terminal.

- [x] Create environment config directory: `sudo mkdir -p /etc/camera-service`
- [x] Write `/etc/camera-service/whiteboard.env` with device path, port, resolution, FPS
- [x] Fix systemd unit file: `${VAR:-default}` bash syntax not supported in `ExecStart` → use `${VAR}` only
- [x] Fix systemd unit file: move `StartLimitBurst`/`StartLimitIntervalSec` to `[Unit]` section
- [x] Copy unit files to `/etc/systemd/system/`
- [x] `sudo systemctl daemon-reload`
- [x] `sudo systemctl enable --now camera-capture@whiteboard`
- [x] `sudo systemctl enable --now camera-api`
- [x] Both services `active (running)` confirmed ✓
- [x] `sudo reboot` — machine rebooted successfully
- [x] `systemctl --failed` → `0 loaded units listed` — nothing broke ✓
- [x] Post-reboot snapshot confirmed without manual intervention ✓

**Definition of done:** ✅ Snapshot works after reboot with no manual intervention.

---

## Step 6 — Second camera (robot) ✅

**Goal:** Add the robot camera so both cameras are available via the API.

- [x] Second StreamCam physically connected via USB-C extension cable
- [x] Both cameras visible: `lsusb` shows two `046d:0893` devices
- [x] **Different serial numbers confirmed** → `by-id` paths usable for both
  - `DA702655` → robot (original camera, USB path `2.1.4`)
  - `51EF0655` → whiteboard (new camera, USB path `2.1.1`)
- [x] Camera assignments were initially swapped → corrected by swapping serial numbers in config
- [x] `/etc/camera-service/robot.env` created (`DA702655`, port 8102)
- [x] `/etc/camera-service/whiteboard.env` updated (`51EF0655`, port 8101)
- [x] `config/production.yaml` updated with both cameras
- [x] `sudo systemctl enable --now camera-capture@robot`
- [x] `sudo systemctl restart camera-capture@whiteboard camera-capture@robot camera-api`
- [x] `GET /readyz` → `{"ready":true,"cameras":{"whiteboard":true,"robot":true}}` ✓
- [x] whiteboard snapshot: **157 kB JPEG** ✓
- [x] robot snapshot: **94 kB JPEG** ✓
- [x] `camera-api.service` updated to `Wants` both capture units

**Definition of done:** ✅ Both cameras respond to independent snapshot requests.

---

## Progress summary

```
Step 1  ✅  Local scaffold + mock API
Step 2  ✅  Hardware inspection
Step 3  ✅  Permissions fix
Step 4  ✅  First real snapshot (118 kB, 1280×720)
Step 5  ✅  systemd — PID 1522/1524, survives reboot
Step 6  ✅  Both cameras live (whiteboard 157 kB, robot 94 kB)
```
