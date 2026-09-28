# Changelog

Reviewed on **2026-09-28**. The current packaged changes are listed under
Unreleased. Older numbered headings are historical development milestones,
not current package-version assertions: `pyproject.toml` and FastAPI metadata
still declare `0.1.0`. Hardware observations, timing numbers and test counts in
those historical entries describe their dates only.

---

## [Unreleased]

### Performance — 2026-09-28

- Offloaded capture filesystem operations and coordinated reads/writes/cleanup.
- Added shared 15-second capture listing and storage-statistics caches.
- Paused hidden previews and unnecessary snapshot/metric/history polling.
- Added cancellable polling without overlapping cycles and timestamped snapshot gaps.
- Added 12 backend and 6 JavaScript regression checks; see
  [PERFORMANCE_UPDATE.md](PERFORMANCE_UPDATE.md) for exact verification limits.

### Removed — 2026-09-28

- Dashboard resolution/target-FPS selectors and mode discovery/write API routes.
- Privileged restart helper, installer, mode-specific reconnection code and tests.
- Read-only source resolution/FPS reporting now lives in the camera HTTP adapter;
  ordinary image controls, saved image configurations and stream metrics remain.
- Added [REMOVAL_NOTES.md](REMOVAL_NOTES.md) for existing lab installations,
  including preservation of saved overrides before removing installed files.

### Documentation — 2026-09-28

- Reviewed all 12 project/ZIP Markdown documents against current routes, frontend
  behavior, settings models, deployment scripts and test files.
- Corrected navigation/hashes, endpoint/auth listings, storage-path distinctions,
  retention timing, missing development config and outdated test references.
- Clarified ping-based readiness, latest-frame snapshot semantics, source target
  FPS versus collector/browser FPS, and the different latency measurements.
- Documented the then-present capture-mode setup; superseded by the removal above.
- Separated historical milestones from current implementation and verification.
- No Python, JavaScript, CSS, YAML, deployment script or dependency changes in
  this documentation update.

### Added

- **API CALLS** at `#api-calls`: operator-protected activity from eligible API
  requests, with a 500-record in-memory buffer and 25/50/100-row display.
- Protected `GET /api/v1/activity` with cursor/session-based incremental retrieval,
  restart detection, request IDs and saved-capture links. Updates run only while
  the page is unlocked and visible. No pause controls or filters.
- API Console at `#api-console`, including request/curl/response copying and
  `GET /openapi.json`. The old `#api` hash remains an alias.
- Settings page with shared-key V4L2 image controls, per-camera cards, previews
  outside the cards and collapsible sections.
- Persistent named image configurations and one-step undo with stale-state checks.
- Header-only stream collector with five-second median/max/count slots, a recent
  latency graph and observed FPS estimate.
- Stream, Snapshots, History and Docs pages, responsive layout, dark/light themes,
  theme-aware syntax highlighting and icon-only Settings navigation.

### Changed

- Saved capture creation is a bodyless per-camera POST, returning a complete JPEG
  URL as plain text and `Location`. Each capture is a flat JPEG/JSON pair.
- Capture listing is newest first by filename time, limited to 1–50 complete
  pairs across both cameras. Statistics count top-level JPG/JSON bytes.
- Retention processes recognized pairs/orphan JPEGs older than 48 hours at startup
  and hourly; directories are left untouched. Folder-based capture compatibility
  was removed.
- `api.public_base_url` supplies the public prefix for returned image URLs.
- Public MJPEG streams in the supplied Nginx snippet bypass FastAPI and proxy
  directly to µStreamer. No fixed end-to-end latency is implied.
- Physical-camera status uses live resolution/desired FPS from µStreamer instead
  of assuming that YAML values describe the active mode.
- Dashboard assets are served from `dashboard/`; matching manual-transfer copies
  are included in the ZIP's separate `JavaScript-text/` folder.

### Access and recording

- The operator model remains one shared environment key. Personal accounts and
  individual revocation are not implemented.
- Activity omits bodies, query strings, credentials, successful marked background
  polls, continuous streams, static assets and its own endpoint. It is transient
  operational history, not an exhaustive audit trail.
- One API worker is required for coherent locks, undo and request history.

### Verification

- Resolution/FPS feature removal: 71 backend tests and three JavaScript suites passed.

- API CALLS implementation: 82 backend tests and all four JavaScript suites passed.
- Full-app mock capture/activity check passed. Synthetic recording overhead was
  about 11 microseconds per request locally; physical-camera performance and
  visual browser rendering were not verified by that test run.
- Current checks and limits: [TESTDOCUMENTATION.md](TESTDOCUMENTATION.md).

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
- The original setup notes recorded unsuccessful SSH login attempts. This is a historical observation, not a current security assessment or proof that all attempts are blocked.

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
- **1280×720 @ 15 fps** chosen for initial deployment on the observed USB 2.0 connection. The initial notes treated 1080p as unreliable; later supplied output reports 1920×1080 MJPEG at 30 FPS, so this was not a permanent device limit.
- **Nginx** as the only public-facing process; µStreamer and FastAPI bind to `127.0.0.1` only.

### Added
- `api/settings.py` — Pydantic-settings YAML loader; reads path from `CAMERA_SERVICE_CONFIG` env var (default: `config/development.yaml`).
- `api/cameras.py` — Camera abstraction layer with `MockCameraSource` (static JPEG from disk) and `UStreamerCameraSource` (HTTP fetch from µStreamer).
- `api/captures.py` — `CaptureStore` class: snapshot disk persistence and JSON sidecars.
- `api/main.py` — FastAPI application with all endpoints:
  - `GET /healthz`
  - `GET /readyz`
  - `GET /api/v1/cameras`
  - `GET /api/v1/cameras/{id}/snapshot.jpg`
  - `GET /api/v1/cameras/{id}/stream.mjpeg`
- `config/development.yaml` — mock camera config pointing at test fixtures; safe to commit.
- `config/production.example.yaml` — template for the real lab config; committed but real file is gitignored.
- `deployment/systemd/camera-capture@.service` — parameterized systemd unit for µStreamer (one instance per camera).
- `deployment/systemd/camera-api.service` — systemd unit for the FastAPI service.
- `deployment/nginx/camera-api.conf` — Nginx camera routing snippet for the existing server. TLS, authentication and redirects are responsibilities of the surrounding Nginx configuration.
- `tests/fixtures/whiteboard.jpg` — 640×480 synthetic JPEG fixture (dark blue, generated with Pillow).
- `tests/fixtures/robot.jpg` — 640×480 synthetic JPEG fixture (dark red, generated with Pillow).
- `tests/conftest.py` — shared pytest fixtures; sets `CAMERA_SERVICE_CONFIG` and overrides captures directory to a temp path.
- `tests/test_api.py` — 14 HTTP endpoint tests (health, cameras list, snapshots, saved captures, error cases).
- `tests/test_cameras.py` — 6 unit tests for `MockCameraSource` and `build_camera_registry`.
- `requirements.txt`
- `pyproject.toml` (pytest config, ruff lint config)
- `README.md`
- `.gitignore`

### Hardware findings (lab.bpm.in.tum.de — 2026-09-18)
- One StreamCam connected: serial `DA702655`
- Stable device path: `/dev/v4l/by-id/usb-046d_Logitech_StreamCam_DA702655-video-index0`
- USB 2.0 (480M) via VIA Labs hubs — initial tested mode: 1280×720, not a proven maximum
- `lab` user missing from `video` group → `sudo usermod -aG video lab` required before deployment
- Second camera not yet physically connected

### Test results (local, mock cameras)
```
20 passed, 2 warnings in 0.09s
```
The initial notes reported this result on Python 3.14.3 and pytest 9.1.1.
Those historical versions are not a current validation of the pinned requirements.

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

When publishing a release, record a dated section and update package/API version
metadata deliberately. Do not treat a documentation-only milestone number as
proof that the package metadata or deployed service has been versioned.
