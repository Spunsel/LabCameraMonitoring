# Lab Server Command History

All commands executed (or planned to be executed) on `lab.bpm.in.tum.de` via SSH.
Organised chronologically by session. Commands that have not yet been run are marked **[PLANNED]**.

---

## Session 1 — 2026-09-18 · Hardware inspection (read-only)

These commands made no changes. They were used to understand the current hardware state.

---

### List all connected USB devices

```bash
lsusb
```

**What it does:** Shows every USB device currently recognised by the kernel, with vendor ID, product ID, and name.
**Result:** One Logitech StreamCam found (`046d:0893`), serial `DA702655`. All other devices are serial converters and USB hubs.

---

### Show USB topology and bus speeds

```bash
lsusb -t
```

**What it does:** Prints the USB device tree including which hub each device is connected through and the negotiated bus speed.
**Result:** The StreamCam is on Bus 001 at **480M (USB 2.0)**, routed through two VIA Labs USB 2.0 hubs. Maximum reliable capture resolution is therefore 1280×720. Bus 002 has a 10000M (USB 3.1) hub available but the camera is not connected to it.

---

### List V4L2 (Video4Linux) capture devices

```bash
v4l2-ctl --list-devices
```

**What it does:** Lists all video capture devices the kernel exposes through the V4L2 subsystem.
**Result:** `Permission denied` — the `lab` user is not yet in the `video` group.

---

### Show stable device paths

```bash
ls -l /dev/v4l/by-id/
```

**What it does:** Lists the persistent, human-readable symlinks that the kernel creates for each camera. These names include the USB vendor, product, and serial number, so they remain the same after a reboot — unlike `/dev/video0` which can change.
**Result:**

```
usb-046d_Logitech_StreamCam_DA702655-video-index0 -> ../../video0
usb-046d_Logitech_StreamCam_DA702655-video-index1 -> ../../video1
```

`-video-index0` is the main capture device used in the config.

---

### Check current group memberships

```bash
groups
```

**What it does:** Lists every group the currently logged-in user belongs to.
**Result:** `lab wheel dialout` — `video` group is missing, which is why V4L2 access is denied.

---

## Session 2 — 2026-09-18 · Permissions fix and first deployment [PLANNED]

---

### Add the lab user to the video group

```bash
sudo usermod -aG video lab
```

**What it does:** Appends (`-aG`) the `lab` user to the `video` group without removing any existing groups. This grants read/write access to `/dev/video*` devices. Takes effect after the next login.
**Risk:** None. Fully reversible with `sudo gpasswd -d lab video`.

---

### Log out to apply the new group

```bash
exit
```

**What it does:** Ends the SSH session. Group membership changes only apply to new login sessions.

---

### Log back in and verify group membership

```bash
ssh lab.bpm.in.tum.de
groups
```

**What it does:** Opens a new session. `groups` should now list `lab wheel dialout video`.

---

### Confirm camera access works

```bash
v4l2-ctl --list-devices
```

**What it does:** Same as before, but should now succeed and print the StreamCam device name and paths.

---

### Deploy project code from local machine

```bash
# Run this from your LOCAL machine, not from lab
rsync -av --exclude='.venv' --exclude='var/' --exclude='.git' \
    /home/christianhorne/CameraMonitoring/ \
    lab.bpm.in.tum.de:~/camera-service/
```

**What it does:** Copies the project files to `~/camera-service/` on lab. Excludes the virtual environment (will be created fresh on lab), runtime captures, and git history. Safe to re-run at any time — rsync only transfers changed files.

---

### Install µStreamer

```bash
sudo dnf install -y ustreamer
```

**What it does:** Installs µStreamer from the Fedora package repository. µStreamer is the process that opens the USB camera device and keeps it open persistently.
**Check first:** Run `dnf search ustreamer` to confirm the package is available before installing.

---

### Create Python virtual environment on lab

```bash
cd ~/camera-service
python3 -m venv .venv
```

**What it does:** Creates an isolated Python environment inside the project folder. Does not affect the system Python.

---

### Install Python dependencies

```bash
.venv/bin/pip install fastapi "uvicorn[standard]" pydantic pydantic-settings httpx PyYAML
```

**What it does:** Installs the FastAPI framework, the Uvicorn ASGI server, Pydantic for config validation, httpx for async HTTP (used to talk to µStreamer), and PyYAML for config file loading. All installed inside `.venv`, not system-wide.

---

### Write the production config

```bash
cat > ~/camera-service/config/production.yaml << 'EOF'
cameras:
  whiteboard:
    source: v4l2
    device: /dev/v4l/by-id/usb-046d_Logitech_StreamCam_DA702655-video-index0
    ustreamer_port: 8101
    width: 1280
    height: 720
    fps: 15

ustreamer:
  whiteboard_port: 8101
  host: "127.0.0.1"

api:
  host: "127.0.0.1"
  port: 8100
  token: ""

storage:
  captures_dir: /home/lab/camera-service/var/captures
EOF
```

**What it does:** Creates the production configuration file (gitignored — never committed). Uses 1280×720 because the camera is connected over USB 2.0 (480M). Both µStreamer and FastAPI are bound to `127.0.0.1` so they are invisible from the network.

---

### Start µStreamer (foreground, for testing)

```bash
ustreamer \
  --device /dev/v4l/by-id/usb-046d_Logitech_StreamCam_DA702655-video-index0 \
  --host 127.0.0.1 --port 8101 \
  --format MJPEG --width 1280 --height 720 --desired-fps 15
```

**What it does:** Starts µStreamer in the foreground. Opens the camera, begins capturing frames, and serves them over HTTP on `127.0.0.1:8101`. Stop with `Ctrl+C`. Bound to localhost only — not reachable from outside.

---

### Start the FastAPI service (foreground, for testing)

```bash
cd ~/camera-service
CAMERA_SERVICE_CONFIG=config/production.yaml \
  .venv/bin/uvicorn api.main:app --host 127.0.0.1 --port 8100
```

**What it does:** Starts the FastAPI camera API in the foreground. Reads `config/production.yaml` to find the camera registry. Listens on `127.0.0.1:8100`. Stop with `Ctrl+C`.

---

### Validate — health check

```bash
curl http://127.0.0.1:8100/healthz
```

**What it does:** Calls the health endpoint. Expected response: `{"status":"ok"}`. Confirms the FastAPI process is running and accepting requests.

---

### Validate — camera readiness

```bash
curl http://127.0.0.1:8100/readyz
```

**What it does:** Checks whether the cameras are delivering frames. Expected response: `{"ready":true,"cameras":{"whiteboard":true}}`. A `503` response means µStreamer is not reachable or the camera is not producing frames.

---

### Validate — real snapshot

```bash
curl http://127.0.0.1:8100/api/v1/cameras/whiteboard/snapshot.jpg -o /tmp/wb.jpg
ls -lh /tmp/wb.jpg
file /tmp/wb.jpg
```

**What it does:**
- Downloads a snapshot JPEG to `/tmp/wb.jpg`
- `ls -lh` confirms file size (expect 30–80 kB for a real frame; a near-zero file means something is wrong)
- `file` confirms it is a valid JPEG (`JPEG image data, ...`)

---

## Session 2 — 2026-09-18 · Filesystem exploration (read-only)

Navigation commands to verify the device tree. No changes made.

### Confirm video devices are present in /dev

```bash
ls /dev
```

**What it does:** Lists all device nodes. Confirms `/dev/video0` and `/dev/video1` are present, meaning the kernel has recognised the StreamCam.
**Result:** Both `video0` and `video1` visible. ✓

### Confirm V4L2 by-id directory exists

```bash
ls /dev/v4l/
```

**What it does:** Confirms the V4L2 stable-path directory structure exists.
**Result:** Both `by-id/` and `by-path/` present. ✓

**Conclusion:** Camera is recognised. Permission is the only remaining blocker — `lab` user is not in the `video` group yet.

---

## Session 3 — 2026-09-18 · Fix video group permissions

### Add lab user to the video group

```bash
sudo usermod -aG video lab
```

**What it does:** Appends the `video` group to the `lab` user's group memberships without touching existing groups (`lab`, `wheel`, `dialout`). Grants read/write access to `/dev/video*` devices.
**Result:** Command succeeded silently (no output = success). ✓

### Log out to apply the new group

```bash
exit
```

**What it does:** Ends the SSH session. Group membership changes only take effect in new login sessions.

### Log back in and verify

```bash
ssh lab
groups
```

**What it does:** Opens a fresh session. `groups` confirms the new membership.
**Result:** `lab wheel dialout video` — `video` group confirmed. ✓

### Confirm camera access now works

```bash
v4l2-ctl --list-devices
```

**What it does:** Lists V4L2 capture devices. Previously returned `Permission denied`.
**Result:**
```
Logitech StreamCam (usb-0000:c3:00.3-2.1.4):
    /dev/video0
    /dev/video1
    /dev/media0
```
Camera accessible. ✓ USB path `c3:00.3-2.1.4` records the physical port location.

---

## Session 4 — 2026-09-18 · Deploy code, install dependencies, first real snapshot ✓

### Sync project files from local machine to lab

```bash
rsync -av \
    --exclude='.venv' \
    --exclude='var/' \
    --exclude='.git' \
    --exclude='LABSERVERCOMMANDS.md' \
    --exclude='CHANGELOG.md' \
    /home/christianhorne/CameraMonitoring/ \
    lab:~/camera-service/
```

**What it does:** Copies source code, config templates, deployment files, and tests to `~/camera-service/` on lab. Excludes the venv (built fresh on lab), runtime captures, git history, and local-only documentation.
**Result:** Transfer successful. ✓

### Check µStreamer availability

```bash
dnf search ustreamer
```

**What it does:** Searches Fedora repos for the ustreamer package before attempting install.
**Result:** `ustreamer.x86_64: Lightweight and fast MJPG-HTTP streamer` found. ✓

### Install µStreamer

```bash
sudo dnf install -y ustreamer
```

**What it does:** Installs µStreamer (version 6.12) from the Fedora package repository.
**Result:** Installed successfully. ✓

### Create Python virtual environment

```bash
cd ~/camera-service
python3 -m venv .venv
```

**What it does:** Creates an isolated Python environment in `~/camera-service/.venv/`. Does not affect the system Python.
**Result:** Created successfully. ✓

### Install Python dependencies

```bash
.venv/bin/pip install fastapi "uvicorn[standard]" pydantic pydantic-settings httpx PyYAML
```

**What it does:** Installs all packages the FastAPI service needs, isolated inside `.venv`.
**Result:** All packages installed successfully (fastapi-0.141.1, uvicorn-0.53.0, pydantic-2.13.5, etc.). ✓

### Write production config

```bash
cat > ~/camera-service/config/production.yaml << 'EOF'
cameras:
  whiteboard:
    source: v4l2
    device: /dev/v4l/by-id/usb-046d_Logitech_StreamCam_DA702655-video-index0
    ustreamer_port: 8101
    width: 1280
    height: 720
    fps: 15

ustreamer:
  whiteboard_port: 8101
  host: "127.0.0.1"

api:
  host: "127.0.0.1"
  port: 8100
  token: ""

storage:
  captures_dir: /home/lab/camera-service/var/captures
EOF
```

**What it does:** Creates the gitignored production config using the stable by-id device path found in Session 1. 1280×720 because the camera is on USB 2.0 (480M).
**Result:** File written to `~/camera-service/config/production.yaml`. ✓

### Start µStreamer (foreground)

```bash
ustreamer \
  --device /dev/v4l/by-id/usb-046d_Logitech_StreamCam_DA702655-video-index0 \
  --host 127.0.0.1 --port 8101 \
  --format MJPEG --resolution 1280x720 --desired-fps 15
```

**What it does:** Opens the StreamCam and begins capturing frames continuously, serving them over HTTP on `127.0.0.1:8101`. Note: `--resolution WxH` is the correct flag (not `--width`/`--height`).
**Result:** `Capturing started` — µStreamer 6.12 running. The `ERROR: Device doesn't support setting of HW encoding quality parameters` line is harmless; the StreamCam handles its own JPEG encoding. ✓

### Start FastAPI service (foreground, second terminal)

```bash
cd ~/camera-service
CAMERA_SERVICE_CONFIG=config/production.yaml \
  .venv/bin/uvicorn api.main:app --host 127.0.0.1 --port 8100
```

**What it does:** Starts the camera API. Reads `config/production.yaml`, builds the camera registry with `UStreamerCameraSource` for `whiteboard`, listens on `127.0.0.1:8100`.
**Result:** `Application startup complete. Uvicorn running on http://127.0.0.1:8100`. ✓

### Validate — health check

```bash
curl http://127.0.0.1:8100/healthz
```

**Result:** `{"status":"ok"}` ✓

### Validate — camera readiness

```bash
curl http://127.0.0.1:8100/readyz
```

**Result:** `{"ready":true,...}` ✓

### Validate — real snapshot from physical camera

```bash
curl http://127.0.0.1:8100/api/v1/cameras/whiteboard/snapshot.jpg -o /tmp/wb.jpg
ls -lh /tmp/wb.jpg
file /tmp/wb.jpg
```

**Result:**
```
-rw-r--r-- 1 lab lab 118K Sep 18 15:29 /tmp/wb.jpg
JPEG image data, comment: "", baseline, precision 8, 1280x720, components 3
```

**118 kB real colour JPEG at 1280×720. First successful snapshot from the physical camera. ✓**

---

## Session 5 — 2026-09-18 · systemd installation and reboot test ✓

### Create the environment config directory

```bash
sudo mkdir -p /etc/camera-service
```

**What it does:** Creates the directory that holds per-camera environment files read by the systemd units.

### Write the whiteboard camera environment file

```bash
sudo tee /etc/camera-service/whiteboard.env << 'EOF'
DEVICE=/dev/v4l/by-id/usb-046d_Logitech_StreamCam_DA702655-video-index0
PORT=8101
RESOLUTION=1280x720
FPS=15
EOF
```

**What it does:** Creates the environment file read by `camera-capture@whiteboard.service`. Each variable maps to a µStreamer command-line argument.

### Install the systemd unit files

```bash
sudo cp ~/camera-service/deployment/systemd/camera-capture@.service /etc/systemd/system/
sudo cp ~/camera-service/deployment/systemd/camera-api.service /etc/systemd/system/
sudo systemctl daemon-reload
```

**What it does:** Copies both unit files to the system-wide location and reloads the systemd config.

### Enable and start both services

```bash
sudo systemctl enable --now camera-capture@whiteboard
sudo systemctl enable --now camera-api
```

**What it does:** Enables both services (auto-start on boot) and starts them immediately.
**Result:** Symlinks created. ✓

### Fix — bash default syntax not supported in ExecStart

```bash
sudo cp ~/camera-service/deployment/systemd/camera-capture@.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl restart camera-capture@whiteboard
```

**What it does:** Fixed `${RESOLUTION:-1280x720}` → `${RESOLUTION}` in the unit file. Systemd does not support bash-style fallback syntax in `ExecStart`.
**Result:** `active (running)`. ✓

### Reboot the lab server

```bash
sudo reboot
```

**What it does:** Verifies both services start automatically. SSH drops immediately — normal.

### Post-reboot verification

```bash
systemctl --failed --no-pager
systemctl status camera-capture@whiteboard camera-api --no-pager
curl http://127.0.0.1:8100/healthz
curl http://127.0.0.1:8100/readyz
curl http://127.0.0.1:8100/api/v1/cameras/whiteboard/snapshot.jpg -o /tmp/post-reboot.jpg
ls -lh /tmp/post-reboot.jpg
```

**Result:**
- `systemctl --failed` → `0 loaded units listed` ✓
- Both services `active (running)` at PID 1522 / 1524 (started at boot) ✓
- `/healthz` → `{"status":"ok"}` ✓
- `/readyz` → `{"ready":true,"cameras":{"whiteboard":true}}` ✓
- Snapshot → 102 kB JPEG ✓

**Step 5 complete. Service survives reboot with no manual intervention. ✓**

---

## Future sessions (not yet run)

| Session | Purpose |
|---|---|
| Session 6 | Connect second camera (robot), add env file, update config |
| Session 7 | Configure Nginx TLS reverse proxy + API token |
| Session 8 | CPEE integration test from demo |
| Session 9 | Full reliability tests (unplug/replug, concurrency) |
