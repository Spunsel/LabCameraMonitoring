# Capture mode

Reviewed against the packaged source on **2026-09-28**.

Each Settings camera card has a collapsed **Capture mode** section with **Resolution**,
**Target FPS**, and **apply**. Selection is staged: changing a selector does not restart
the camera. Apply asks for confirmation because it briefly interrupts this camera's feed
for every viewer.

The selectors are built from `v4l2-ctl --list-formats-ext` for the configured device.
Only discrete MJPEG resolutions and whole-number FPS values are offered; unsupported
combinations, fractional values, arbitrary device paths, and unknown camera IDs are
rejected. The supplied StreamCam output advertises 30, 24, 20, 15, 10 and 5 FPS in
MJPEG, plus 7.5 FPS. Discovery reads the device at request time. The reported 7.5 FPS
mode is deliberately omitted because this implementation uses uStreamer's integer
`--desired-fps` setting. Format remains MJPEG; there is no format or quality selector.

## Install on the lab server

Copy the changed project files into `/home/lab/camera-service`, retaining your existing
production YAML, virtual environment, operator key, camera environment files, and
captures. Make sure both existing capture services are running, then:

```bash
cd /home/lab/camera-service
sudo bash deployment/setup-capture-mode.sh
```

Reload the browser after setup. This script:

1. Verifies the capture services use `--resolution=${RESOLUTION}` and
   `--desired-fps=${FPS}`, as in your existing unit.
2. Reads each running process's actual device and port to build a root-owned
   policy for `whiteboard` and `robot`. The API YAML device paths and ports must
   match these entries.
3. Installs a root-owned standalone helper at
   `/usr/local/libexec/camera-capture-mode`.
4. Grants the API service user permission to run **only that helper** using
   passwordless sudo. It does not grant general systemctl or shell access.
5. Adds an optional environment-file override to each capture service, reloads
   systemd and restarts the API. Setup itself does not restart the captures.

The helper depends only on system Python, systemctl and v4l2-ctl. No additional Python
packages beyond the application requirements are needed. The script expects
`/usr/bin/python3`, `/usr/bin/systemctl`, `/usr/bin/sudo`, `/usr/bin/v4l2-ctl`, and
`visudo` on PATH. Re-running setup updates its installed files and preserves saved
capture-mode overrides.

Until setup is installed, the section can display discovered/current modes but its
controls stay disabled with a setup-unavailable message. Existing image controls retain
their current operator-key setup. No personal-key changes are part of this feature.

## Reverse-proxy timeout

The bundled `deployment/nginx/camera-api.conf` still uses `proxy_read_timeout 30s` for
FastAPI. The API helper call can wait up to 65 seconds, and the Settings request allows
90 seconds. A slow restart/rollback can therefore outlast the proxy timeout. When
enabling this feature, update the active `/cameras/` FastAPI location to
`proxy_read_timeout 90s;`, then validate and reload Nginx. Preserve that override when
merging later template updates.

```bash
sudoedit /etc/nginx/cpee.d/locations.d/camera
sudo nginx -t
sudo systemctl reload nginx
```

This documentation change does not modify the bundled Nginx template or the lab server.
A timeout does not prove that the mode change failed: refresh the camera state before
retrying. Do not interrupt the server transaction to retry blindly.

## Persistence and application

The helper writes only these per-camera overrides:

```text
/etc/camera-service/capture-modes/whiteboard.env
/etc/camera-service/capture-modes/robot.env
```

Each contains `RESOLUTION=...` and `FPS=...`. It is loaded after the original capture
environment file, so these values take precedence and survive service restarts/reboots.
The original environment files and production YAML are not rewritten. The dashboard
status endpoint reads active resolution and target FPS from µStreamer `/state`, avoiding
stale YAML values after a change. For physical cameras it returns `null` mode fields
when the online mode cannot be read/validated. The code requires a positive integer
desired FPS; a reported zero (maximum/unspecified target) is not accepted as a current
mode.

Applying restarts only `camera-capture@<camera>.service`, then verifies the online
source's resolution and desired FPS. This verifies the reported mode, not sustained
observed/browser FPS. If restart or verification fails, the helper restores the previous
override (or removes the new override if none existed), restarts that capture service
again, and reports whether recovery was confirmed. API operations are serialized with
existing image-control changes, and the helper has a separate per-camera process lock. A
stale request is rejected if its expected previous mode no longer matches.

The API snapshots active image settings before the restart and restores them when
necessary afterwards. Automatically controlled focus/exposure/white balance remain
automatic. Any restoration/readback failure is reported rather than claiming success.
The image-control undo slot is cleared after validation and before a real mode-change
transaction starts. Invalid/stale requests and an already- matching mode return before
that clearing step. Saved image configurations and **restore defaults** cover image
controls; capture mode has its own persistent apply operation and is not part of those
presets or the image-control undo stack.

The Settings preview reconnects after applying. Active previews retry on image errors,
and status polling reconnects active previews when it detects a changed mode. Hidden
pages do not acquire new stream connections. Preview images fit inside their boxes
without cropping when a 4:3 or other aspect ratio is selected. Captures saved before the
change are unchanged; subsequent snapshots use the new source resolution. Actual FPS can
be below the target, depending on exposure, USB bandwidth and load. Changing the target
does not promise an exact measured frame rate.

## API

- `GET /api/v1/cameras/{camera_id}/controls/capture-mode`: current mode,
  supported resolution/FPS combinations and write availability.
- `PATCH /api/v1/cameras/{camera_id}/controls/capture-mode`: requires the existing
  `X-Camera-Control-Key` header. Example body:

```json
{
  "mode": {"width": 1280, "height": 720, "fps": 15},
  "expected": {"width": 1920, "height": 1080, "fps": 30}
}
```

Success returns image-control readback plus `capture_mode`. Validation and stale-state
failures do not restart anything. Apply failures include readback when available. A
disconnected browser does not cancel an in-progress restart transaction. Keep the
existing single-worker API deployment.

## Verification

```bash
python -m pytest tests/test_capture_modes.py tests/test_controls.py tests/test_camera_configs.py tests/test_captures.py
node tests/test_capture_mode_ui.mjs
node tests/test_controls_ui.mjs
node tests/test_api_console.mjs
bash -n deployment/setup-capture-mode.sh
```

Hardware/systemd operations are simulated in automated tests. After installation, verify
on one camera: save your image configuration, apply a supported mode, check the live
preview/new snapshot and change back to your intended mode. A real systemd restart and
visual browser rendering require the lab installation.

## Installed files and updates

Setup also installs `/etc/camera-service/capture-mode-policy.json`,
`/etc/sudoers.d/camera-capture-mode`, and
`/etc/systemd/system/camera-capture@<camera>.service.d/90-capture-mode.conf`. The helper
uses per-camera locks in `/run/camera-service-mode/`. Inspect the effective unit with
`systemctl cat`, including its drop-ins.

After changing the packaged helper/setup code, rerun `sudo bash
deployment/setup-capture-mode.sh` from the installed project to update the root-owned
helper. Copying the Python application alone does not update it. After replacing a
camera or changing its port/device mapping, update the base capture configuration and
API YAML together, restart the affected capture service, then rerun setup to rebuild the
policy from the running processes.

See [SERVER_LAYOUT.md](SERVER_LAYOUT.md) for the full file map and
[TESTDOCUMENTATION.md](TESTDOCUMENTATION.md) for integrated checks.
