# Changelog

All notable changes to the camera-service project are recorded here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versions follow [Semantic Versioning](https://semver.org/).

---

## [Unreleased]

### Capture API migration
- [x] Capture creation uses a bodyless `POST /api/v1/cameras/{camera_id}/captures`. One camera is selected by the URL; each POST saves one JPEG with a generated event ID and returns the complete image URL as plain text and in `Location`.
- [x] Removed the old `POST /api/v1/captures` route, JSON capture request, caller-supplied event ID, and JSON POST response. `GET /api/v1/captures` still lists images and metadata.
- [x] Added `api.public_base_url` to configure the public Nginx prefix in returned image links. Updated the dashboard button, Docs tab, and API examples.

### Added
- [x] `GET /api/v1/status` — returns per-camera availability, resolution, fps, and API uptime; latency is measured client-side
- [x] `GET /dashboard` — live monitoring dashboard at `https://lab.bpm.in.tum.de/cameras/dashboard`
- [x] `dashboard/` — HTML, CSS, and JavaScript for the three dashboard sections: **STREAM**, **CAPTURES**, and **RECENT CAPTURES**

### Fixed
- [x] Replaced `assert _store is not None` (3×) with `HTTPException(503)` — asserts can be silently disabled with `python -O`
- [x] `api/cameras.py`: removed unused `import asyncio`, `import time`, and `self._last_ok` tracking
- [x] `readyz()`, `list_cameras()`, `get_status()` now ping both cameras in parallel via `asyncio.gather` instead of sequentially

### Changed
- [x] Dashboard CSS and JavaScript now live in `dashboard/assets/`; Adwaita Mono and the extracted History download icon are served from its `fonts/` and `icons/` folders
- [x] Dashboard assets moved out of `api/dashboard.py` into `dashboard/`; FastAPI serves the page and its CSS/JS separately, including when the app is proxied under `/cameras`
- [x] `GET /api/v1/captures`: now returns `list[dict]` with rich metadata (`event_id`, `captured_at`, per-camera file sizes in bytes); sorted by mtime (most recent first); accepts `?limit=N` (1–50, default 10) — was `list[str]` capped at 20
- [x] `deployment/nginx/camera-api.conf`: MJPEG stream endpoints bypass FastAPI and proxy directly to µStreamer (:8101/:8102) — stream latency drops from ~150–300 ms to ~30–80 ms
- [x] `config/production.example.yaml`: default FPS raised 15 → 30 (USB 2.0 handles 720p @ 30 fps without issue)
- [x] Dashboard: snapshot latency measured client-side via `performance.now()` + `await fetch()` TTFB; frame size from `blob.size` — no server-side measurement needed
- [x] Dashboard: canvas bar chart — 30-minute sliding window (360 slots × 5 s), bars right-aligned and color-coded green/yellow/red, dashed white average line with value label
- [x] Dashboard: `Cache-Control: no-store` on all snapshot responses → no `?t=` cache-buster needed in JS
- [x] Dashboard: capture list polls `GET /api/v1/captures?limit=50` and filters per camera client-side; re-renders only when event ID changes; configurable rows (1–50, default 10) per camera table with immediate re-render on change
- [x] Dashboard: polling intervals — status every 30 s, snapshot latency every 5 s, captures every 15 s
- [x] Rsync-lab alias: corrected exclude from `LABSERVERCOMMANDS.md` → `LAB_COMMANDS.md`

---

## [0.4.0] — 2026-09-18 · Both cameras live ✅

### Hardware
- Second StreamCam (serial `51EF0655`) connected via USB-C extension cable.
- Both cameras have **different serial numbers** → stable `by-id` paths usable for both.
- Camera assignments were initially swapped; corrected by swapping serials in config (no hardware change needed).

### Final camera assignment
| Name | Serial | USB path | Port |
|---|---|---|---|
| whiteboard | `51EF0655` | `2.1.1` | 8101 |
| robot | `DA702655` | `2.1.4` | 8102 |

### Deployment
- `/etc/camera-service/robot.env` created.
- `/etc/camera-service/whiteboard.env` updated with correct serial.
- `config/production.yaml` updated with both cameras.
- `camera-capture@robot.service` enabled and started.
- `camera-api.service` updated: `Wants` now references both capture units.

### Validated
- `GET /readyz` → `{"ready":true,"cameras":{"whiteboard":true,"robot":true}}` ✓
- whiteboard snapshot: 157 kB JPEG ✓
- robot snapshot: 94 kB JPEG ✓

---

## [0.3.0] — 2026-09-18 · systemd automatic startup confirmed ✅

### Deployment
- Created `/etc/camera-service/whiteboard.env` with device path, port, resolution, FPS.
- Installed `camera-capture@.service` and `camera-api.service` to `/etc/systemd/system/`.
- Both services enabled and running: `systemctl enable --now`.
- `sudo reboot` performed — `systemctl --failed` returned `0 loaded units listed` post-reboot.
- Camera snapshot confirmed after reboot without manual intervention.

### Fixed
- systemd `ExecStart`: removed `${VAR:-default}` bash fallback syntax (not supported by systemd) — use plain `${VAR}` and always set values in the `.env` file.
- systemd: moved `StartLimitBurst` and `StartLimitIntervalSec` from `[Service]` to `[Unit]` section (correct location per systemd spec).

### Security (observation — not actioned)
- Lab server is receiving ongoing SSH brute-force attempts from external IPs. All are blocked. Worth reporting to lab admin for `fail2ban` or network-level SSH restriction.

---

## [0.2.0] — 2026-09-18 · First real camera snapshot on lab ✓

### Hardware
- µStreamer 6.12 installed via `sudo dnf install -y ustreamer` from standard Fedora repos.
- StreamCam produces 118 kB JPEG frames at 1280×720 over USB 2.0. Confirmed real colour image.
- Harmless startup warning: `Device doesn't support setting of HW encoding quality parameters` — StreamCam handles its own JPEG encoding internally; frames are delivered correctly.

### Deployment
- Project code deployed to `~/camera-service/` on lab via `rsync`.
- Python venv created at `~/camera-service/.venv/` with all deps installed.
- `config/production.yaml` written with single whiteboard camera using stable `/dev/v4l/by-id/` path.
- µStreamer and FastAPI running in foreground (manual start — systemd comes next).

### Fixed
- rsync command: use `lab:` SSH alias instead of `lab.bpm.in.tum.de:` to avoid `Permission denied` when local username differs from server username.
- µStreamer resolution flag: `--resolution 1280x720` not `--width 1280 --height 720`.

### Validated on lab
- `GET /healthz` → `{"status":"ok"}` ✓
- `GET /readyz` → `{"ready":true}` ✓
- `GET /api/v1/cameras/whiteboard/snapshot.jpg` → 118 kB JPEG, 1280×720, colour ✓

---

## [0.1.0] — 2026-09-18 · Initial scaffold

### Context
Project started from scratch in `/home/christianhorne/CameraMonitoring`.
Goal: replace ad-hoc ngrok-based camera scripts with a single, permanent,
documented camera gateway service on `lab.bpm.in.tum.de`.

### Architecture decisions made
- **µStreamer** chosen as the capture daemon (one process per camera, owns the USB device, handles reconnects, serves JPEG/MJPEG over HTTP).
- **FastAPI** chosen as the API layer (typed, auto-documented, async, easy to test without hardware).
- **Interchangeable camera sources** (`MockCameraSource` / `UStreamerCameraSource`) so the full API can be developed and tested locally without physical cameras.
- **Config-driven** (YAML + `pydantic-settings`): switching from mock to real camera requires only a config change, not a code change.
- **`/dev/v4l/by-id/` paths** used in production config instead of `/dev/video0` (stable across reboots).
- **1280×720 @ 15 fps** chosen for lab deployment because the StreamCam is on USB 2.0 (480M); 1080p is unreliable at that bandwidth.
- **Nginx** as the only public-facing process; µStreamer and FastAPI bind to `127.0.0.1` only.

### Added
- `api/settings.py` — Pydantic-settings YAML loader; reads path from `CAMERA_SERVICE_CONFIG` env var (default: `config/development.yaml`).
- `api/cameras.py` — Camera abstraction layer with `MockCameraSource` (static JPEG from disk) and `UStreamerCameraSource` (HTTP fetch from µStreamer).
- `api/captures.py` — `CaptureStore` class: concurrent dual-camera snapshot, disk persistence, metadata JSON side-car.
- `api/main.py` — FastAPI application with all endpoints:
  - `GET /healthz`
  - `GET /readyz`
  - `GET /api/v1/cameras`
  - `GET /api/v1/cameras/{id}/snapshot.jpg`
  - `GET /api/v1/cameras/{id}/stream.mjpeg`
  - `POST /api/v1/captures`
  - `GET /api/v1/captures/{event_id}`
  - `GET /api/v1/captures/{event_id}/{camera_id}.jpg`
- `config/development.yaml` — mock camera config pointing at test fixtures; safe to commit.
- `config/production.example.yaml` — template for the real lab config; committed but real file is gitignored.
- `deployment/systemd/camera-capture@.service` — parameterized systemd unit for µStreamer (one instance per camera).
- `deployment/systemd/camera-api.service` — systemd unit for the FastAPI service.
- `deployment/nginx/camera-api.conf` — Nginx reverse proxy config (TLS, auth, MJPEG streaming, HTTP→HTTPS redirect).
- `tests/fixtures/whiteboard.jpg` — 640×480 synthetic JPEG fixture (dark blue, generated with Pillow).
- `tests/fixtures/robot.jpg` — 640×480 synthetic JPEG fixture (dark red, generated with Pillow).
- `tests/conftest.py` — shared pytest fixtures; sets `CAMERA_SERVICE_CONFIG` and overrides captures directory to a temp path.
- `tests/test_api.py` — 14 HTTP endpoint tests (health, cameras list, snapshots, event captures, error cases).
- `tests/test_cameras.py` — 6 unit tests for `MockCameraSource` and `build_camera_registry`.
- `requirements.txt`
- `pyproject.toml` (pytest config, ruff lint config)
- `README.md`
- `.gitignore`

### Hardware findings (lab.bpm.in.tum.de — 2026-09-18)
- One StreamCam connected: serial `DA702655`
- Stable device path: `/dev/v4l/by-id/usb-046d_Logitech_StreamCam_DA702655-video-index0`
- USB 2.0 (480M) via VIA Labs hubs — max reliable: 1280×720
- `lab` user missing from `video` group → `sudo usermod -aG video lab` required before deployment
- Second camera not yet physically connected

### Test results (local, mock cameras)
```
20 passed, 2 warnings in 0.09s
```
All tests green on Python 3.14.3, pytest 9.1.1.

### Git
```
commit 4fef53f  Initial project scaffold
commit 8a6eab9  gitignore: exclude .venv
```

---

## How to add an entry

When you make a change, add a block at the top of the **[Unreleased]** section using these tags:

- **Added** — new files, endpoints, features
- **Changed** — changes to existing behaviour or config
- **Fixed** — bug fixes
- **Removed** — deleted files or endpoints
- **Security** — auth or access control changes
- **Hardware** — physical changes on lab (cables, cameras, USB ports)
- **Deployment** — systemd, Nginx, server config changes

When a milestone is reached (e.g. "working on lab with one camera"), move the Unreleased block to a new versioned section like `[0.2.0] — YYYY-MM-DD`.
