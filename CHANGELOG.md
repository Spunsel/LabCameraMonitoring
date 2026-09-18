# Changelog

All notable changes to the camera-service project are recorded here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versions follow [Semantic Versioning](https://semver.org/).

---

## [Unreleased] — on lab.bpm.in.tum.de

Changes that have been developed locally but not yet deployed to the lab server.

### Planned
- Production deployment with real V4L2 / µStreamer camera source
- systemd units for automatic startup (`camera-capture@whiteboard`, `camera-api`)
- Nginx TLS reverse proxy at `https://lab.bpm.in.tum.de/camera-api/`
- API token authentication enabled
- Second camera (`robot`) connected and configured
- CPEE integration test from demo/coruscant

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
