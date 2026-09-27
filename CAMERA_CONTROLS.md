# Camera controls

Camera settings have a dedicated Settings tab between Snapshots and Docs.
It contains two camera columns, each with a live preview and four independently
collapsible control sections, all closed by default, and one compact operator
unlock/lock toolbar above both columns. Click a section heading or focus it and
press Enter/Space to expand or collapse it. Expand/collapse SVG icons indicate
the state in both themes. Normal control readbacks preserve open sections.
A lock icon with View mode or a pencil icon with Edit mode beside Camera settings
shows access status as plain text, without a button border or background.
View mode is blue and Edit mode is green; the SVG icon and text use the same
theme-aware color. The title and operator-access form share a 2rem minimum
height, with the title stretching to match the form when they share a row.
Common adjustments appear first. Automatic-mode switches sit beside the related
manual controls; refresh is beside each camera name and restore defaults is at
the bottom of each column. Refresh uses the same button style as Capture snapshot.
Focus/exposure, white balance/gain, and backlight compensation/variable frame rate
are paired left/right. The columns and paired controls stack on narrow screens.
Stream and Snapshots retain their previews and metrics without settings panels.
`dashboard/assets/controls.js` exports the `CameraControlsPanel` and
`CameraControlsAccess` classes; `settings.js` builds the page and manages previews.
Settings streams connect only while the Settings tab is active.

## Enable on the existing lab server

Copy the updated project files into `/home/lab/camera-service`, keeping the
existing virtual environment and production YAML. Then run:

```bash
cd /home/lab/camera-service
sudo bash deployment/setup-controls.sh
```

The script requires the already installed `v4l2-ctl`, creates an operator key
if none exists, grants the API supplementary `video` group access, and restarts
only `camera-api.service`. It uses a systemd drop-in, preserving the existing
unit. It prints the operator key for the dashboard. Re-running it preserves
that key. If necessary, first install `v4l-utils` with
`sudo apt install v4l-utils` on Debian/Ubuntu.

Check that the active `config/production.yaml` uses the same devices as the
capture services. The supplied server output identifies:

```yaml
cameras:
  whiteboard:
    source: v4l2
    device: /dev/v4l/by-id/usb-046d_Logitech_StreamCam_51EF0655-video-index0
  robot:
    source: v4l2
    device: /dev/v4l/by-id/usb-046d_Logitech_StreamCam_DA702655-video-index0
```

These are just the relevant YAML keys: preserve existing ports, resolution,
FPS, storage and other settings. The API uses YAML device paths, not the capture
services' `.env` files. No Python dependency changes are needed.

Reload the dashboard, open Settings, enter the key at the top, and click **unlock controls**.
Unlock applies to both cameras for the current page session. **Lock controls**
clears it. The key stays in memory and is sent in `X-Camera-Control-Key`, so it
does not conflict with existing Nginx Basic authentication. Without a configured
server key, settings remain readable and writes are disabled. Use the existing
HTTPS dashboard when entering the key remotely.

## Controls and behavior

| Section | Controls |
| --- | --- |
| Focus & exposure | Focus with Auto switch; exposure with Auto switch |
| Framing | Zoom; pan and tilt |
| Image tuning | White balance with Auto switch; brightness, contrast, saturation, sharpness, gain |
| Lighting & frame rate | Anti-flicker, backlight compensation, variable frame rate |

Only supported, allowlisted controls appear. Ranges, increments, defaults, menus
and availability come from the camera. Exposure is displayed in ms; pan/tilt
use the V4L2 degree conversion; white balance uses Kelvin. Zoom and focus retain
the device's numeric scale. Zoom `100–400` is not an optical magnification
guarantee. Pan/tilt may shift a cropped image only after zooming in; verify the
visible effect on the physical cameras.

Manual focus, exposure and white balance are disabled while their automatic mode
is active. Change the mode first. Sliders send one request on release; number
fields apply on Enter/blur. Refresh occurs when entering Settings, after
each change, or with **refresh** beside the camera name. Controls display camera readback values.
Snapshot previews retain their five-second refresh interval.

Changes affect the camera, all streams and future snapshots. Existing captures
are unchanged. **Restore camera defaults** restores the driver's reported
defaults, including automatic modes. It is not an undo operation; Logitech's
default anti-flicker can be 60 Hz. Your output reported 60 Hz for whiteboard and
50 Hz for robot; choose 50 Hz if appropriate for lab lighting. Variable frame
rate can reduce FPS in low light.

The API does not reset settings at startup or store presets. Hardware settings
can reset after USB reconnection, power loss or another program's changes;
refresh to read actual values. Failed multi-control requests can partially
apply: responses identify completed writes and include readback when available.
The dashboard reports the failure and refreshes state.

## API

| Method and path | Purpose |
| --- | --- |
| `GET /api/v1/cameras/{camera_id}/controls` | Read supported settings and `write_enabled` |
| `GET /api/v1/cameras/{camera_id}/controls/access` | Validate an operator key |
| `PATCH /api/v1/cameras/{camera_id}/controls` | Apply `{"values":{"name":integer}}` and return readback |
| `POST /api/v1/cameras/{camera_id}/controls/reset` | Restore camera defaults and return readback |

All except the first require `X-Camera-Control-Key`. API values use native V4L2
integers: exposure is in 0.1 ms units, pan/tilt in arcseconds. The API validates
every requested value before writes and serializes operations per camera.
Automatic-mode changes run before dependent manual values. It executes
`v4l2-ctl` asynchronously with fixed arguments, without a shell. Ordinary
control changes do not restart µStreamer.

```bash
curl -fsS http://127.0.0.1:8100/api/v1/cameras/whiteboard/controls
read -rsp 'Operator key: ' CAMERA_CONTROLS_KEY
printf '\n'
curl -fsS -X PATCH \
  -H "X-Camera-Control-Key: $CAMERA_CONTROLS_KEY" \
  -H 'Content-Type: application/json' \
  -d '{"values":{"focus_automatic_continuous":0,"focus_absolute":30}}' \
  http://127.0.0.1:8100/api/v1/cameras/whiteboard/controls
unset CAMERA_CONTROLS_KEY
```

Errors: 403 invalid key, 404 unknown camera, 409 inactive/manual-mode conflict,
422 invalid value, 503 missing setup/device access or rejected driver operation,
504 device timeout. Mock cameras report settings as unavailable rather than
pretending to apply them. FastAPI's `/docs` also lists the routes.

## Verification

Run `python -m pytest tests/test_controls.py` and `node tests/test_controls_ui.mjs`.
The JavaScript test uses a DOM stand-in; it is not a visual browser test.
Backend tests use a fixture based on the
supplied StreamCam output and a fake device runner. On the lab hardware, test
one camera while watching its live feed: adjust zoom/pan/tilt, switch to manual
focus, and change exposure/white balance. Readback verifies acceptance; visual
inspection verifies the effect. Restore your desired settings and check that
streaming and new captures continue. Automated tests cannot prove how the
physical camera firmware implements each advertised control.
