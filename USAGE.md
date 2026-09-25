# Usage — extra commands

Grab-bag of **one-off, high-value commands** that came up while building and
debugging this project but that don't belong in the more structured docs
below. Check those first — this file only has what's *not* already there.

| Doc | What's in it |
|---|---|
| [`README.md`](README.md) | Setup, deployment, endpoint reference table |
| [`TESTDOCUMENTATION.md`](TESTDOCUMENTATION.md) | Structured pass/fail tests (T-01…T-16) |
| [`LAB_COMMANDS.md`](LAB_COMMANDS.md) | systemd / journalctl / nginx / hardware debug commands (German) |
| [`SERVER_LAYOUT.md`](SERVER_LAYOUT.md) | File-to-purpose map, request-flow diagrams |

---

## 1 · Manually triggering a capture

There are two ways to take a snapshot through the REST API. Replace
`whiteboard` with `robot` in either example to use the other camera.

**Mode 1 — take a picture and return its JPEG immediately (no disk storage):**

```bash
curl -fsS 'https://lab.bpm.in.tum.de/cameras/api/v1/cameras/whiteboard/snapshot.jpg' \
  -o whiteboard.jpg
```

The response is `image/jpeg`, not JSON. Every request takes a new picture;
there is no stored link or History entry for this mode.

**Mode 2 — take a picture, save it, and return a link:**

```bash
saved_url=$(curl -fsS -X POST \
  'https://lab.bpm.in.tum.de/cameras/api/v1/cameras/whiteboard/captures')
printf '%s\n' "$saved_url"
curl -fsS "$saved_url" -o whiteboard.jpg
```

The bodyless POST returns `201 Created`. Its `text/plain` body contains the
complete stored JPEG URL; the same URL appears in the `Location` response
header. Configure `api.public_base_url` in `config/production.yaml` as
`https://lab.bpm.in.tum.de/cameras` so the URL works through Nginx. If unset,
the URL uses the incoming request address (useful for local development).

Stored captures become eligible for removal after 48 hours. Cleanup runs at
startup and hourly, so a link can remain valid for up to one more hour; it
returns `404` after deletion. POST always saves one selected image; use Mode 1
when you want the JPEG directly in the response.

The dashboard's **capture snapshot** button uses Mode 2. Select one camera
in the URL for each POST. The server generates each event ID; store the
returned URL alongside your CPEE activity if you need a correlation key.

**Whiteboard:**
```bash
curl -fsS -X POST https://lab.bpm.in.tum.de/cameras/api/v1/cameras/whiteboard/captures
```

**Robot (another request and generated event ID):**
```bash
curl -fsS -X POST https://lab.bpm.in.tum.de/cameras/api/v1/cameras/robot/captures
```

**Directly on the lab server** (skips Nginx/TLS):
```bash
curl -fsS -X POST http://127.0.0.1:8100/api/v1/cameras/whiteboard/captures
```

The previous `POST /api/v1/captures` route has been removed. Including
any request body, including the former JSON selector, returns `400`.

To confirm the capture on disk, derive its generated event ID from the saved
URL. The JPEG filename follows `<camera>_YYYYMMDDTHHMMSSmmmZ.jpg` (UTC):
```bash
# On lab, after running the Mode 2 example above:
capture_event_id=$(basename "$(dirname "$saved_url")")
# Set this to storage.captures_dir from your active config:
capture_storage_dir=/var/lib/camera-service/captures
ls -la "$capture_storage_dir/$capture_event_id"/
cat "$capture_storage_dir/$capture_event_id"/metadata.json | python3 -m json.tool
```

---

## 2 · Inspecting µStreamer's per-frame latency headers

The stream metrics graph (`GET /api/v1/stream-metrics`) is built on
µStreamer's `X-UStreamer-*` headers. To see the raw headers yourself (on lab,
via SSH):

```bash
curl -s --max-time 2 "http://127.0.0.1:8101/?action=stream&extra_headers=1&zero_data=1" \
  | grep -i "ustreamer"
```
Swap `8101` → `8102` for the robot camera.

`zero_data=1` means **no JPEG bytes are sent** — only headers — so this is a
near-zero-bandwidth way to sample latency by hand. Key fields:

| Header | Meaning |
|---|---|
| `X-UStreamer-Grab-Time` | When the frame was captured off the sensor |
| `X-UStreamer-Encode-Begin/End-Time` | JPEG encode window |
| `X-UStreamer-Send-Time` | When µStreamer started sending the frame |
| `X-UStreamer-Latency` | `Send-Time − Grab-Time`, in **seconds** (multiply by 1000 for ms) — this is what the dashboard graphs as "capture-to-send latency" |

**Check the live collector is actually running** (the background task started
in `api/main.py`'s lifespan):
```bash
sudo journalctl -u camera-api -n 30 --no-pager | grep -i stream-metrics
# Expect to see:
#   stream-metrics: collector started for whiteboard → http://127.0.0.1:8101/...
#   stream-metrics: collector started for robot → http://127.0.0.1:8102/...
#   stream-metrics whiteboard: connected
#   stream-metrics robot: connected
```

**Query the aggregated endpoint directly** (same data the dashboard polls
every 5 s):
```bash
curl -s http://127.0.0.1:8100/api/v1/stream-metrics | python3 -m json.tool
```

---

## 3 · Measuring real (glass-to-glass) stream latency

Neither TTFB nor `X-UStreamer-Latency` capture true "camera to eyeball"
latency — browsers buffer a few MJPEG frames before rendering, and that part
is invisible to any server-side timer. The only reliable way to measure it is
the **stopwatch method** used by AV engineers:

**Step 1 — show a live millisecond clock in the camera's field of view**
(run on lab, in front of whichever camera you're testing):
```bash
watch -n 0.1 date '+%H:%M:%S.%3N'
```

**Step 2 — open the stream in a browser** next to that terminal:
```
https://lab.bpm.in.tum.de/cameras/dashboard
```

**Step 3 — screenshot both at once.** The difference between the wall-clock
time and the time shown in the video feed is the true glass-to-browser
latency. (No camera view of a terminal handy? A phone stopwatch app held up
to the lens works just as well.)

**Server-side floor only — time to first frame (TTFF)** — how fast µStreamer
delivers one full frame after a fresh connection (does **not** include
browser buffering):
```bash
python3 -c "
import urllib.request, time
url = 'http://127.0.0.1:8101/?action=stream'   # 8102 for robot
t0 = time.perf_counter()
with urllib.request.urlopen(url, timeout=5) as r:
    buf = b''
    while True:
        buf += r.read(4096)
        if b'\xff\xd9' in buf:   # JPEG end-of-image marker
            print(f'TTFF: {(time.perf_counter()-t0)*1000:.0f} ms')
            break
"
```

---

## 4 · TTFB vs. full download time

The dashboard's "snapshot download time" measures `await r.blob()`
completion, not `fetch()`-resolves (which is only TTFB). This curl command
compares the two directly, `N` times, to confirm they're nearly identical on
localhost (i.e. any spread you see is real network/server variance, not a
measurement artifact):

```bash
for i in $(seq 40); do
  curl -s -o /dev/null -w "%{time_starttransfer} %{time_total}\n" \
    http://127.0.0.1:8100/api/v1/cameras/whiteboard/snapshot.jpg
done | awk '{ttfb+=$1; total+=$2; n++} END {
  printf "avg TTFB:   %.1f ms\navg TOTAL:  %.1f ms\ndiff:       %.1f ms\n",
    ttfb/n*1000, total/n*1000, (total-ttfb)/n*1000
}'
```

---

## 5 · Dashboard deep links

The dashboard's tabs are URL-hash based, so any of these can be
bookmarked or shared directly:

```
https://lab.bpm.in.tum.de/cameras/dashboard#live         # Stream tab (default)
https://lab.bpm.in.tum.de/cameras/dashboard#snapshots    # Snapshots tab
https://lab.bpm.in.tum.de/cameras/dashboard#history      # History (recent captures) tab
```

---

## 6 · Verifying dashboard edits before deploying

The page lives in `dashboard/index.html`, with CSS, JavaScript, the font, and
the download icon in `dashboard/assets/`. The API serves them from `/dashboard` and `/dashboard/assets/`. There is
no build step. Before `rsync-lab`, check the JavaScript and Python syntax:

```bash
node --check dashboard/assets/app.js
.venv/bin/python -m py_compile api/main.py

.venv/bin/python -c "from api.main import app; print('app builds OK')"

# After starting/restarting the API, confirm all three files are reachable.
curl -fsS http://127.0.0.1:8100/dashboard | grep -q 'dashboard/assets/app.js'
curl -fsS http://127.0.0.1:8100/dashboard/assets/styles.css | grep -q '#recent-grid'
curl -fsS http://127.0.0.1:8100/dashboard/assets/app.js | grep -q 'const CAMERAS'
curl -fsSI http://127.0.0.1:8100/dashboard/assets/fonts/adwaita-mono-regular.ttf
curl -fsS http://127.0.0.1:8100/dashboard/assets/icons/download.svg | grep -q '<svg'
```

When deploying this split for the first time, copy the `dashboard/` folder and
the updated `api/main.py` together, remove the old `api/dashboard.py`, then
restart `camera-api`. Check `/cameras/dashboard` through Nginx afterward;
the public `/cameras/dashboard/assets/` paths must reach FastAPI too.
