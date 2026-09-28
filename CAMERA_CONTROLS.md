# Camera controls

Reviewed against the packaged source on **2026-09-28**.

Camera settings have an icon-only entry beside the theme toggle. It contains two camera
columns, each with a live preview and four independently collapsible image-control
sections, all closed by default, and one compact operator unlock/lock
toolbar above both columns. Click a section heading or focus it and use the browser's
keyboard activation (typically Enter or Space) to expand or collapse it. Expand/collapse
SVG icons indicate the state in both themes. Normal control readbacks preserve open
sections. A lock icon with View mode or a pencil icon with Edit mode beside Camera
settings shows access status as plain text, without a button border or background. View
mode is blue and Edit mode is green; the SVG icon and text use the same theme-aware
color. The title and operator-access form share a 2rem minimum height, with the title
stretching to match the form when they share a row. Common adjustments appear first.
Automatic-mode switches sit beside the related manual controls; refresh is beside each
camera name and restore defaults is at the bottom of each column. Refresh uses the same
button style as Capture snapshot. Focus/exposure, white balance/gain, and backlight
compensation/variable frame rate are paired left/right. The columns and paired controls
stack on narrow screens. Stream and Snapshots retain their previews and metrics without
settings panels. `dashboard/assets/controls.js` exports the `CameraControlsPanel` and
`CameraControlsAccess` classes; `settings.js` builds the page and manages previews.
Settings streams connect only while the Settings tab is active.

## Enable on the existing lab server

Copy the updated project files into `/home/lab/camera-service`, keeping the existing
virtual environment and production YAML. Then run:

```bash
cd /home/lab/camera-service
sudo bash deployment/setup-controls.sh
```

The script requires the already installed `v4l2-ctl`, creates an operator key if none
exists, grants the API supplementary `video` group access, and restarts only
`camera-api.service`. It uses a systemd drop-in, preserving the existing unit. It prints
the operator key for the dashboard. Re-running it preserves that key. If necessary,
first install `v4l-utils` with `sudo apt install v4l-utils` on Debian/Ubuntu or `sudo
dnf install v4l-utils` on Fedora.

Check that the active `config/production.yaml` uses the same devices as the capture
services. The supplied server output identifies:

```yaml
cameras:
  whiteboard:
    source: v4l2
    device: /dev/v4l/by-id/usb-046d_Logitech_StreamCam_51EF0655-video-index0
  robot:
    source: v4l2
    device: /dev/v4l/by-id/usb-046d_Logitech_StreamCam_DA702655-video-index0
```

These are just the relevant YAML keys: preserve existing ports, resolution, FPS, storage
and other settings. The API uses YAML device paths, not the capture services' `.env`
files. No Python dependency changes are needed.

Reload the dashboard, open Settings, enter the key at the top, and click **unlock
controls**. Unlock applies to both cameras for the current page session. **Lock
controls** clears it. The key stays in memory and is sent in `X-Camera-Control-Key`, so
it does not conflict with existing Nginx Basic authentication. Without a configured
server key, supported physical-camera settings remain readable and protected requests
return 503. Mock-camera settings return 409 because no V4L2 device exists. Use the
existing HTTPS dashboard when entering the key remotely.

## Controls and behavior

| Section | Controls |
| --- | --- |
| Focus & exposure | Focus with Auto switch; exposure with Auto switch |
| Framing | Zoom; pan and tilt |
| Image tuning | White balance with Auto switch; brightness, contrast, saturation, sharpness, gain |
| Lighting & frame rate | Anti-flicker, backlight compensation, variable frame rate |

Only supported, allowlisted controls appear. Ranges, increments, defaults, menus and
availability come from the camera. Exposure is displayed in ms; pan/tilt are displayed
in degrees (3600 native arcseconds per degree); white balance uses Kelvin. Zoom and
focus retain the device's numeric scale. Zoom `100–400` is not an optical magnification
guarantee. Pan/tilt may shift a cropped image only after zooming in; verify the visible
effect on the physical cameras.

Manual focus, exposure and white balance are disabled while their automatic mode is
active. Change the mode first. Sliders send one request on release; number fields apply
on Enter/blur. Refresh occurs when entering Settings, after each change, or with
**refresh** beside the camera name. Controls display camera readback values. Snapshot
previews retain their five-second refresh interval.

Changes affect the camera, all streams and future snapshots. Existing captures are
unchanged. **Restore defaults** restores the driver's reported defaults for supported,
eligible writable controls, including automatic modes. Defaults are read with `v4l2-ctl
--list-ctrls-menus` at reset time; they are not hardcoded in the dashboard or YAML.
Read-only, disabled, grabbed and inactive controls are skipped, as are manual values
whose restored mode is automatic. The current response reports readback and adjusted
values, not a complete restored/skipped audit list. This is not a factory reset,
restoration of a previous setup, or a reset of capture resolution/FPS. Logitech's
default anti-flicker can be 60 Hz. Variable frame rate can reduce FPS in low light.

The API does not reset settings or automatically load a configuration at startup.
Hardware settings can reset after USB reconnection, power loss or another program's
changes; refresh to read actual values. Failed multi-control requests can partially
apply: responses identify completed writes and include readback when available. The
dashboard reports the failure and refreshes state.

## Save, load and undo

Each camera footer has **save config** and **load config** on the left, and **restore
defaults** followed by an icon-only **undo** button on the right. All require unlocked
operator access. The previews and refresh buttons stay above and outside the settings
card.

- **save config** opens a name field with **save** and **discard**. It reads the
  camera's current settings without modifying them. Names are trimmed, limited
  to 80 characters, and unique per camera (case insensitive). Existing names
  are never silently overwritten.
- **load config** lists that camera's saved names. Selecting one opens a
  confirmation with **switch** and **abort**. Only **switch** changes hardware.
- **undo** restores the configuration immediately before your last change,
  including reset or loading a saved configuration. It is one step, not a
  history or redo stack. It cannot reconstruct changes for which no valid undo record/token remains.
  Refresh and saving a configuration do not consume undo. Reloading the browser,
  locking controls, or restarting the API clears this session's undo access.
  A later image-control mutation invalidates
  older undo tokens; changed writable values detected from another program also
  block undo. Changes that return to the same observed state cannot be detected. Reapplying already-matching values can leave the
  existing undo slot intact. A failed batch reports partial changes and offers
  recovery when readback is available.

Automatic focus, exposure and white balance remain automatic when saved that way. Their
changing measurements are not stored as manual settings. Loading a manual configuration
switches modes first, then restores the manual values. Values are validated against
current camera capabilities before any write. The driver can adjust requested values;
the dashboard shows the readback and reports adjustments rather than claiming an exact
restoration.

Configurations persist as JSON in a separate `camera-configs` directory beside
`storage.captures_dir` (`var/camera-configs` with the model default, or
`/var/lib/camera-service/camera-configs` with the production template). Capture
retention does not remove them. The API service account needs write access to that
directory or its parent for first creation. To choose another location, add the optional
`storage.camera_configs_dir` setting to the existing YAML. Files are written atomically,
and names never become file paths. Configurations are tied to both the camera ID and its
configured device path. Back up this directory with your installation. The UI/API
currently has no configuration rename or delete action. Listing configuration names
requires the operator key; public control readbacks expose neither names nor undo
tokens.

Copy the updated application files into the existing installation, preserving production
YAML, the operator key, and saved captures. Restart only the API:

```bash
sudo systemctl restart camera-api.service
```

Then reload the dashboard for frontend changes. A documentation-only update needs no
restart. For ordinary image-control updates, no additional Python dependencies or
capture-service restart are required. Keep the existing **one Uvicorn
worker** deployment: per-camera write locks and one-step undo state are in the API
process.

## API

| Method and path | Purpose |
| --- | --- |
| `GET /api/v1/cameras/{camera_id}/controls` | Read supported settings and `write_enabled` |
| `GET /api/v1/cameras/{camera_id}/controls/access` | Validate an operator key |
| `PATCH /api/v1/cameras/{camera_id}/controls` | Apply `{"values":{"name":integer}}` and return readback |
| `POST /api/v1/cameras/{camera_id}/controls/reset` | Restore eligible driver-reported image-control defaults and return readback |
| `GET /api/v1/cameras/{camera_id}/controls/configs` | List saved names, IDs and creation dates |
| `POST /api/v1/cameras/{camera_id}/controls/configs` | Save current settings with `{"name":"Lab baseline"}` |
| `POST /api/v1/cameras/{camera_id}/controls/configs/{config_id}/load` | Apply a saved configuration |
| `POST /api/v1/cameras/{camera_id}/controls/undo` | Undo using `{"undo_token":"…"}` from the preceding mutation |

Mutation responses include a private `undo_token` when recovery is available. Public
reads include a `revision` used to invalidate stale dashboard undo state. Save responses
also include the refreshed `configs` list and `saved_config_id`.

All except the first require `X-Camera-Control-Key`. API values use native V4L2
integers: exposure is in 0.1 ms units, pan/tilt in arcseconds. The API validates every
requested value before writes and serializes operations per camera. Automatic-mode
changes run before dependent manual values. It executes `v4l2-ctl` asynchronously with
fixed arguments, without a shell. Ordinary control changes do not restart µStreamer.

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

Errors: 403 invalid key, 404 unknown camera, 409 inactive/manual-mode conflict, 422
invalid value, 503 missing setup/device access or rejected driver operation, 504 device
timeout. Mock cameras report settings as unavailable rather than pretending to apply
them. FastAPI's `/docs` and `/openapi.json` also list the routes; the dashboard's
`#docs` page is a separate snapshot integration guide.

## Verification

Run `python -m pytest tests/test_controls.py tests/test_camera_configs.py` and `node
tests/test_controls_ui.mjs`. The JavaScript test uses a DOM stand-in; it is not a visual
browser test. Backend tests use a fixture based on the supplied StreamCam output and a
fake device runner. On the lab hardware, test one camera while watching its live feed:
adjust zoom/pan/tilt, switch to manual focus, and change exposure/white balance.
Readback verifies acceptance; visual inspection verifies the effect. Restore your
desired settings and check that streaming and new captures continue. Automated tests
cannot prove how the physical camera firmware implements each advertised control.

## Shared-key access and restarts

The current implementation reads one shared `CAMERA_SERVICE_CONTROLS_TOKEN` at API
startup. Individual operator accounts, key hashes, per-person revocation and operator
attribution are not implemented. Changing the shared key requires an API restart,
invalidates use of the old key, and clears in-memory undo, API activity and stream
metrics. Saved configurations remain on disk.

Settings, API Console and API CALLS have separate in-memory key inputs. Unlocking one
does not unlock the others. The same server key authorizes their protected operations;
Nginx website authentication is a separate access layer.

For the complete test matrix, see [TESTDOCUMENTATION.md](TESTDOCUMENTATION.md).
