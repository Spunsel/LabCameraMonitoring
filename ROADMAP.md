# Project Roadmap

Camera monitoring service for the BPM Lab at TU München.
Tracks every milestone from initial scaffold to full production deployment.

---

## Legend

| Symbol | Meaning |
|---|---|
| ✅ | Completed |
| 🔲 | Not yet started |
| ⚡ | Next immediate action |

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

## Step 6 — Second camera (robot) 🔲

**Goal:** Add the robot camera so both cameras are available via the API.

**Prerequisite:** USB-C extension cable (SuperSpeed 5 Gbit/s data, not charging-only) must be physically installed first.

- [ ] Connect second StreamCam to lab via extension cable
- [ ] Confirm it appears: `lsusb`, `v4l2-ctl --list-devices`
- [ ] Record its stable by-id path: `ls -l /dev/v4l/by-id/`
- [ ] If both cameras have the same serial number: use `/dev/v4l/by-path/` and label the USB ports physically
- [ ] Add `robot` camera to `config/production.yaml`
- [ ] Add and start `camera-capture@robot.service`
- [ ] `GET /readyz` → `{"ready":true,"cameras":{"whiteboard":true,"robot":true}}` ✓
- [ ] Visual confirmation: snapshot from robot camera shows the robot

**Definition of done:** Both cameras respond to independent snapshot requests with the correct scene.

---

## Step 7 — Nginx TLS reverse proxy + API token 🔲

**Goal:** The service is reachable at a stable HTTPS URL from outside the machine, with authentication.

- [ ] Inspect the existing Nginx config on lab: `sudo nginx -T 2>&1 | grep -E 'server_name|listen|location|proxy_pass'`
- [ ] Determine the target URL (e.g. `https://lab.bpm.in.tum.de/camera-api/`)
- [ ] Copy `deployment/nginx/camera-api.conf` to `/etc/nginx/conf.d/`
- [ ] Adjust `server_name` and SSL certificate paths to match the existing TUM setup
- [ ] Generate a strong API token: `openssl rand -hex 32`
- [ ] Set `token:` in `config/production.yaml`
- [ ] `sudo nginx -t && sudo systemctl reload nginx`
- [ ] Test with token: `curl -H "Authorization: Bearer <token>" https://lab.bpm.in.tum.de/camera-api/healthz`
- [ ] Test that requests without token are rejected with `401`
- [ ] Test that MJPEG stream (`stream.mjpeg`) flows without buffering

**Definition of done:** `https://lab.bpm.in.tum.de/camera-api/api/v1/cameras/whiteboard/snapshot.jpg` returns a JPEG with a valid token. No token → 401.

---

## Step 8 — CPEE integration test 🔲

**Goal:** A real CPEE process on demo/coruscant can trigger a capture and receive image URLs.

- [ ] Confirm demo can reach lab: `curl --connect-timeout 5 https://lab.bpm.in.tum.de/camera-api/healthz` (from demo)
- [ ] Create a minimal CPEE test workflow with one HTTP activity:
  - Method: `POST`
  - URL: `https://lab.bpm.in.tum.de/camera-api/api/v1/captures`
  - Header: `Authorization: Bearer <token>`
  - Body: `{"event_id": "cpee-test-001", "cameras": ["whiteboard", "robot"], "store": true}`
- [ ] Run the workflow and confirm the response contains image URLs
- [ ] Download the captured images from the returned URLs and confirm they are correct

**Definition of done:** CPEE workflow completes with `201` and valid image URLs pointing to real lab photos.

---

## Step 9 — Reliability and acceptance tests 🔲

**Goal:** Verify the service survives real-world failure conditions before declaring it production-ready.

- [ ] **Reboot test** — `sudo reboot`; after restart both cameras respond within 60 seconds
- [ ] **Unplug whiteboard camera** — `/readyz` returns `503` within a few seconds; logs show disconnect
- [ ] **Replug whiteboard camera** — µStreamer reconnects; `/readyz` returns `200` again without manual intervention
- [ ] **Concurrent snapshot requests** — run 5 `curl` commands simultaneously; all return valid JPEGs
- [ ] **Invalid token** — `curl` without token returns `401`, not `500`
- [ ] **Unknown camera** — `GET /api/v1/cameras/nonexistent/snapshot.jpg` returns `404`
- [ ] **Capture directory full** (simulate) — service returns meaningful error, does not crash
- [ ] **Professor walkthrough** — demonstrate framing and image quality; adjust camera position if needed

**Definition of done:** All failure cases handled cleanly. Professor has approved image framing. Old ngrok endpoints can be retired.

---

## After Step 9 — Future work (out of scope for now)

| Item | Why deferred |
|---|---|
| Fedora 41 → 42 upgrade | Separate maintenance window; needs server admin coordination |
| Continuous recording | Introduces storage, retention, and privacy requirements |
| WebRTC / HLS live stream | Can be added later without changing the public URL structure |
| MQTT-triggered capture | Only needed if existing CPEE models already use MQTT |
| Privacy / data protection review | Coordinate with TUM data-protection contact before any recording |

---

## Progress summary

```
Step 1  ✅  Local scaffold + mock API
Step 2  ✅  Hardware inspection
Step 3  ✅  Permissions fix
Step 4  ✅  First real snapshot (118 kB, 1280×720)
Step 5  ✅  systemd — automatic startup + reboot confirmed
Step 6  ⚡  Second camera (robot)                ← NEXT
Step 7  🔲  Nginx TLS + API token
Step 8  🔲  CPEE integration
Step 9  🔲  Reliability tests + professor sign-off
```
