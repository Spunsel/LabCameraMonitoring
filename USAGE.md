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

This is exactly what the dashboard's **capture snapshot** button does under
the hood (`POST /api/v1/captures`) — handy for testing without opening a
browser.

**Both cameras at once** (omit `"cameras"` to capture everything):
```bash
curl -sS -X POST https://lab.bpm.in.tum.de/cameras/api/v1/captures \
  -H "Content-Type: application/json" \
  -d '{"event_id": "manual-test-1", "store": true}' \
  | python3 -m json.tool
```

**A single camera:**
```bash
curl -sS -X POST https://lab.bpm.in.tum.de/cameras/api/v1/captures \
  -H "Content-Type: application/json" \
  -d '{"event_id": "manual-test-2", "cameras": ["whiteboard"], "store": true}' \
  | python3 -m json.tool
```

**Directly on the lab server** (skips Nginx/TLS):
```bash
curl -sS -X POST http://127.0.0.1:8100/api/v1/captures \
  -H "Content-Type: application/json" \
  -d '{"event_id": "manual-test-3", "store": true}' \
  | python3 -m json.tool
```

The response includes `filenames` — the real on-disk name for each camera
(`<camera>_YYYYMMDDTHHMMSSmmmZ.jpg`, UTC, millisecond precision). Confirm it
landed on disk:
```bash
# On lab, after running one of the above:
ls -la ~/camera-service/var/captures/manual-test-1/
cat  ~/camera-service/var/captures/manual-test-1/metadata.json | python3 -m json.tool
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

## 6 · Verifying `api/dashboard.py` edits before deploying

`api/dashboard.py` is one large Python string containing HTML/CSS/JS with no
build step or linter of its own, so a quick sanity pass before every
`rsync-lab` catches typos that would otherwise only surface in the browser:

```bash
.venv/bin/python -c "
from api.dashboard import DASHBOARD_HTML as h
script = h.split('<script>')[1].split('</script>')[0]
assert script.count('{') == script.count('}'), 'brace mismatch'
assert script.count('(') == script.count(')'), 'paren mismatch'
print('brace/paren balance OK')
"

# Confirm the whole app still imports cleanly (catches Python-side breakage too)
.venv/bin/python -c "from api.main import app; print('app builds OK')"
```
