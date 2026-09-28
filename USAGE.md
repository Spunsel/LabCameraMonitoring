# Usage and measurement guide

Reviewed against the packaged source on **2026-09-28**. Run SSH examples on the
lab server unless marked as public-client examples. See [README.md](README.md)
for installation, [LAB_COMMANDS.md](LAB_COMMANDS.md) for diagnosis, and
[TESTDOCUMENTATION.md](TESTDOCUMENTATION.md) for verification.

## Current JPEG or saved capture

These operations retrieve a frame from the running source. They do not trigger
a synchronized exposure, and successive requests can receive the same frame.

Public-client example, current JPEG with no API-side storage:

```bash
curl -fsS 'https://lab.bpm.in.tum.de/cameras/api/v1/cameras/whiteboard/snapshot.jpg' \
  -o whiteboard.jpg
```

Public-client example, save one image and then download it:

```bash
saved_url=$(curl -fsS -X POST \
  'https://lab.bpm.in.tum.de/cameras/api/v1/cameras/whiteboard/captures')
printf '%s\n' "$saved_url"
curl -fsS "$saved_url" -o whiteboard.jpg
```

If the website requires Basic authentication, add `--user 'your-website-username'`
to each public curl command and enter the password when prompted. That login is
separate from the camera operator key. The capture operations themselves do not
require `X-Camera-Control-Key`.

The bodyless POST returns **201 Created**, a complete URL as `text/plain`, and the
same URL in `Location`. A nonempty request body returns 400. The dashboard's
**capture snapshot** button uses this saved mode. Select `robot` in the URL for
the other camera; each POST saves just one image. There is no experiment-ID
parameter; a CPEE workflow can store the returned URL alongside its own run ID.

`api.public_base_url` should be `https://lab.bpm.in.tum.de/cameras` in production.
It is not set in the supplied production template. If absent, the API builds
links from the request base, which can lose the public proxy prefix.

The same API can be called locally over SSH, without Nginx:

```bash
camera_api_base=http://127.0.0.1:8100
saved_url=$(curl -fsS -X POST "$camera_api_base/api/v1/cameras/robot/captures")
capture_filename=${saved_url##*/}
metadata_filename=${capture_filename%.jpg}.json
curl -fsS "$camera_api_base/api/v1/captures/$capture_filename" -o /tmp/robot-saved.jpg
curl -fsS "$camera_api_base/api/v1/captures/$metadata_filename" | python3 -m json.tool
```

Using the filename with the local base works even when POST returns a public URL.
To inspect the pair on disk, resolve storage from the active configuration:

```bash
cd /home/lab/camera-service
capture_storage_dir=$(CAMERA_SERVICE_CONFIG=config/production.yaml .venv/bin/python -c \
  'from api.settings import load_settings; print(load_settings().storage.captures_dir.resolve())')
ls -lh "$capture_storage_dir/$capture_filename" "$capture_storage_dir/$metadata_filename"
python3 -m json.tool "$capture_storage_dir/$metadata_filename"
```

## Filenames, timestamps and retention

| Value | Meaning |
| --- | --- |
| `<camera>_YYYYMMDDTHHMMSSmmmZ.jpg` | UTC filename, with millisecond precision |
| Matching `.json` | Metadata and completion marker for the JPEG/JSON pair |
| Metadata `captured_at` | API timestamp after receiving and inspecting the JPEG |
| Snapshot `X-Captured-At` | API timestamp generated for that direct JPEG response |
| Filename collision adjustment | Advance to the next unused millisecond; metadata keeps its receive time |

None of these timestamps is a hardware exposure timestamp. Stored metadata also
includes filename, camera ID, image size in bytes, dimensions and content type.

Recognized pairs and orphan JPEGs become eligible for cleanup after 48 hours,
based on the filename time. Cleanup runs at API startup and hourly. Expiry does
not immediately block retrieval: links return 404 after deletion or if the pair
is incomplete/invalid. Downtime or cleanup errors can delay removal beyond the
next hour. Subdirectories and symlinks are ignored. Saved camera configurations
live separately and are not removed by capture cleanup.

History fetches the newest **50 captures across both cameras**, then displays up
to the selected 1–50 rows per camera (default 10). Selecting 50 does not guarantee
50 per camera if the combined result contains fewer for that camera. Its storage
summary covers all top-level JPG/JSON files, not just the visible rows, and is
not a measure of remaining disk space.

## Timing and FPS: what the numbers mean

| Display / measurement | Interval measured |
| --- | --- |
| Snapshot “time to first byte” | Browser request start until `fetch()` resolves with response headers; a browser-side approximation |
| Snapshot “download time” | Request start until the complete JPEG blob has been received; includes the first-byte wait |
| API Console elapsed time | Browser request start until the response body is received |
| API CALLS duration | API middleware arrival until the final body message is sent to the ASGI server; can include server backpressure |
| Stream “capture-to-send latency” | µStreamer's reported `X-UStreamer-Latency`, converted from seconds to milliseconds |
| Stream “actual fps” | Valid distinct frame headers counted in the latest aggregation slot, divided by five seconds |
| Target FPS | Desired capture rate from µStreamer `/state`, not measured delivery rate |

These values are not interchangeable. None alone measures sensor-to-browser
visual delay. “Actual fps” is an estimate at the collector, not browser-rendered
FPS; exposure, reconnects, invalid headers and load can affect it.

The stream collector keeps a persistent header-only connection to each physical
camera's µStreamer instance. It deduplicates grab timestamps and collects five-
second median/max/count slots. Up to 360 nonempty slots are retained in API
memory; the dashboard plots timestamps within the most recent 30-minute window.
Missing intervals create gaps. This is not a new camera request every five
seconds. Mock cameras do not create µStreamer collectors.

## Inspect µStreamer and stream metrics

```bash
# Header-only stream; timeout is intentional because the response is continuous.
curl -sS --max-time 2 \
  'http://127.0.0.1:8101/?action=stream&extra_headers=1&zero_data=1' \
  | grep -i 'X-UStreamer-'

# Current µStreamer state; replace 8101 with 8102 for robot.
curl -fsS http://127.0.0.1:8101/state | python3 -m json.tool

# Aggregated metrics: reads API memory without triggering a new camera request.
curl -fsS http://127.0.0.1:8100/api/v1/stream-metrics | python3 -m json.tool

# Collector connection/reconnection messages.
sudo journalctl -u camera-api.service -n 100 --no-pager | grep -i stream-metrics
```

`zero_data=1` omits JPEG payloads but still transfers MIME/frame headers. The
collector recognizes `X-UStreamer-Grab-Time` and `X-UStreamer-Grab-Begin-Time` for
deduplication, requires `X-UStreamer-Online: true`, and uses the reported latency
value. Those timing fields are µStreamer timestamps, not wall-clock exposure
metadata. The bounded curl command normally exits with timeout code 28.

## Compare snapshot request timings

```bash
# Forty sequential requests on lab; seconds, bytes, status.
for i in $(seq 40); do
  curl -sS -o /dev/null \
    -w 'ttfb=%{time_starttransfer} total=%{time_total} bytes=%{size_download} status=%{http_code}\n' \
    http://127.0.0.1:8100/api/v1/cameras/whiteboard/snapshot.jpg
done
```

Replace the camera or public URL to compare paths. Check HTTP status and size
before interpreting timings. Total time includes TTFB; `total - ttfb` approximates
the remaining body-transfer time. There is no fixed expected millisecond value,
and localhost measurements do not predict public-network performance.

For a continuous MJPEG response, curl TTFB measures the start of the HTTP
response, not completion or display of the first JPEG. To estimate visual
camera-to-display latency, film a rapidly updating clock and compare its direct
view with the displayed camera view in the same observation. Clock refresh,
monitor refresh and camera exposure limit precision. A clock updating every
100 ms cannot reliably resolve a difference of a few tens of milliseconds.

## Polling and visibility

| Function | Current behavior |
| --- | --- |
| API uptime/status | Polled at load and every 30 seconds; uptime text ticks locally each second |
| Snapshot measurement/previews | At load and every 5 seconds, including when another dashboard page is active |
| Stream metrics | At load and every 5 seconds, including other dashboard pages |
| History list/statistics | On entry, every 15 seconds while History is active, and after saves/row-limit changes |
| Stream and Settings live previews | Disconnect when their dashboard page is inactive |
| API CALLS | Polls while unlocked and both its page and browser tab are visible; next request 5 seconds after completion |
| Camera controls | On entering Settings, manual refresh and relevant changes; not continuously polled |

Browser timer throttling can affect these intervals. Only API CALLS explicitly
uses browser-tab visibility to stop its polling; that behavior should not be
assumed for the other pages. Automatic status/metrics/history/snapshot fetches
are tagged so successful polls do not fill API CALLS.

## Dashboard deep links

| Page | Public URL |
| --- | --- |
| Stream | [Stream](https://lab.bpm.in.tum.de/cameras/dashboard#stream) |
| Snapshots | [Snapshots](https://lab.bpm.in.tum.de/cameras/dashboard#snapshots) |
| History | [History](https://lab.bpm.in.tum.de/cameras/dashboard#history) |
| Docs | [Docs](https://lab.bpm.in.tum.de/cameras/dashboard#docs) |
| API Console | [API Console](https://lab.bpm.in.tum.de/cameras/dashboard#api-console) |
| API CALLS | [API CALLS](https://lab.bpm.in.tum.de/cameras/dashboard#api-calls) |
| Settings | [Settings](https://lab.bpm.in.tum.de/cameras/dashboard#settings) |

The older `#api` link still opens API Console. Access to API CALLS needs the
existing shared operator key; see [API_CALLS.md](API_CALLS.md).

## Verify assets after deployment

There is no frontend build step. Serve the dashboard through FastAPI/Nginx for
functional verification; opening the HTML as a local file is not an API test.

```bash
cd /home/lab/camera-service
for asset in dashboard/assets/*.js; do node --check "$asset"; done
.venv/bin/python -m compileall -q api

curl -fsS http://127.0.0.1:8100/dashboard | grep -q 'panel-api-calls'
curl -fsS http://127.0.0.1:8100/dashboard/assets/app.js | grep -q 'setApiCallsActive'
curl -fsS http://127.0.0.1:8100/dashboard/assets/api-console.js | grep -q 'ApiConsole'
curl -fsS http://127.0.0.1:8100/dashboard/assets/api-calls.js | grep -q 'ApiCalls'
curl -fsSI http://127.0.0.1:8100/dashboard/assets/fonts/adwaita-mono-regular.ttf
```

Node is needed for syntax checks only. Deploy API and dashboard code together for
feature updates, restart `camera-api.service` if backend files changed, and hard-
refresh the browser for frontend changes. Markdown-only updates need no restart.
