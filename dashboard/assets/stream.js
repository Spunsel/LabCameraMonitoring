import { BASE, CAMERAS, CAM_LABEL, TOTAL_SLOTS, latCls } from './common.js';
import { drawBarGraph, STREAM_GRAPH_OPTS } from './charts.js';

// Stream capture-to-send latency history per camera (stream graph)
// Full 360-slot array — null means no data for that 5-second slot.
const streamHist = {};
CAMERAS.forEach(id => streamHist[id] = new Array(TOTAL_SLOTS).fill(null));

// ── Build stream cards (stream image + capture latency graph) ──────────
const sg = document.getElementById('stream-grid');
CAMERAS.forEach(id => {
  const d = document.createElement('div');
  d.innerHTML = `
    <div class="cam-lbl"><span class="dot" id="dot-${id}">●</span>${CAM_LABEL[id]}</div>
    <div class="img-box">
      <img id="stream-img-${id}" data-src="${BASE}/api/v1/cameras/${id}/stream.mjpeg"
           src="${BASE}/api/v1/cameras/${id}/stream.mjpeg" alt="${id}">
    </div>
    <div class="cam-bottom">
      <div class="cam-stats">
        <table class="mt">
          <tr><td class="k">capture-to-send latency</td><td id="stream-lat-${id}" class="m">—</td></tr>
          <tr><td class="k">stream status</td><td id="stream-state-${id}" class="m">—</td></tr>
          <tr><td class="k">fps config</td><td id="stream-fps-${id}">—</td></tr>
        </table>
      </div>
      <div class="cam-divider"></div>
      <div class="cam-graph">
        <canvas id="graph-stream-${id}"></canvas>
      </div>
    </div>`;
  sg.appendChild(d);
});

// ── Stream metrics polling (every 5 s) ───────────────────────────────
// Converts the API's timestamped slot list into a full TOTAL_SLOTS array
// where each index maps to a specific 5-second window ending at "now".
// Gaps (windows with no valid frames) remain null.
function buildTimestampedHistory(history, intervalSeconds) {
  const result = new Array(TOTAL_SLOTS).fill(null);
  if (!history.length) return result;
  const now = Date.now() / 1000;
  const windowStart = now - intervalSeconds * TOTAL_SLOTS;
  history.forEach(slot => {
    const idx = Math.floor((slot.timestamp - windowStart) / intervalSeconds);
    if (idx >= 0 && idx < TOTAL_SLOTS) result[idx] = slot.median_ms;
  });
  return result;
}

const STATE_CLS = { live: 'g', starting: 'm', stale: 'w', offline: 'b', disconnected: 'b' };

export async function pollStreamMetrics() {
  let data;
  try {
    const r = await fetch(`${BASE}/api/v1/stream-metrics`);
    if (!r.ok) throw new Error();
    data = await r.json();
  } catch { return; }

  for (const id of CAMERAS) {
    const cam = data.cameras?.[id];
    if (!cam) continue;

    const stateEl = document.getElementById(`stream-state-${id}`);
    if (stateEl) {
      stateEl.textContent = cam.state;
      stateEl.className   = STATE_CLS[cam.state] ?? 'm';
    }

    const latEl = document.getElementById(`stream-lat-${id}`);
    if (latEl) {
      if (cam.latest) {
        const ms = Math.round(cam.latest.median_ms);
        latEl.textContent = `${ms} ms`;
        latEl.className   = latCls(ms);
      } else {
        latEl.textContent = '—';
        latEl.className   = 'm';
      }
    }

    const hist = buildTimestampedHistory(cam.history, data.interval_seconds);
    streamHist[id] = hist;
    drawBarGraph(`graph-stream-${id}`, hist, STREAM_GRAPH_OPTS);
  }
}

// The single status request in app.js supplies data to both camera pages.
export function updateStreamStatus(data) {
  if (!data) {
    CAMERAS.forEach(id => document.getElementById('dot-' + id).className = 'dot off');
    return;
  }
  for (const [id, cam] of Object.entries(data.cameras)) {
    document.getElementById('dot-' + id).className = 'dot ' + (cam.available ? 'on' : 'off');
    const fpsEl = document.getElementById('stream-fps-' + id);
    if (fpsEl) fpsEl.textContent = cam.fps != null ? cam.fps + ' fps' : '—';
  }
}

export function redrawStreamGraphs() {
  CAMERAS.forEach(id => drawBarGraph('graph-stream-' + id, streamHist[id], STREAM_GRAPH_OPTS));
}

export function setStreamActive(active) {
  CAMERAS.forEach(id => {
    const img = document.getElementById('stream-img-' + id);
    if (!img) return;
    if (active) {
      if (!img.getAttribute('src')) img.src = img.dataset.src;
    } else {
      // A hidden MJPEG image would otherwise keep its server connection open.
      img.removeAttribute('src');
    }
  });
  if (active) redrawStreamGraphs();
}
