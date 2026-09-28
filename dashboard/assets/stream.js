import { BASE, CAMERAS, CAM_LABEL, TOTAL_SLOTS, latCls, retryLivePreview } from './common.js';
import { drawBarGraph, STREAM_GRAPH_OPTS } from './charts.js';

const streamHist = {};
CAMERAS.forEach(id => streamHist[id] = new Array(TOTAL_SLOTS).fill(null));

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
          <tr><td class="k">actual fps</td><td id="stream-fps-${id}" title="Distinct frames observed from µStreamer per second over the latest 5-second interval; browser display FPS is not measured.">—</td></tr>
          <tr><td class="k">resolution</td><td id="stream-res-${id}">—</td></tr>
        </table>
      </div>
      <div class="cam-divider"></div>
      <div class="cam-graph">
        <canvas id="graph-stream-${id}"></canvas>
      </div>
    </div>`;
  sg.appendChild(d);
  retryLivePreview(document.getElementById(`stream-img-${id}`));
});

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
    const r = await fetch(`${BASE}/api/v1/stream-metrics`, { headers: { 'X-Camera-Background': '1' } });
    if (!r.ok) throw new Error();
    data = await r.json();
  } catch {
    CAMERAS.forEach(id => document.getElementById(`stream-fps-${id}`).textContent = '—');
    return;
  }

  for (const id of CAMERAS) {
    const cam = data.cameras?.[id];
    if (!cam) {
      document.getElementById(`stream-fps-${id}`).textContent = '—';
      continue;
    }

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

    const fpsEl = document.getElementById(`stream-fps-${id}`);
    const latest = cam.latest;
    const fresh = latest && (Date.now() / 1000 - latest.timestamp) < 2 * data.interval_seconds;
    if (fpsEl) {
      fpsEl.textContent = cam.state === 'live' && fresh && Number.isFinite(latest.count)
        ? `${(latest.count / data.interval_seconds).toFixed(1)} fps`
        : '—';
    }

    const hist = buildTimestampedHistory(cam.history, data.interval_seconds);
    streamHist[id] = hist;
    drawBarGraph(`graph-stream-${id}`, hist, STREAM_GRAPH_OPTS);
  }
}

export function updateStreamStatus(data) {
  if (!data) {
    CAMERAS.forEach(id => {
      document.getElementById('dot-' + id).className = 'dot off';
      document.getElementById('stream-res-' + id).textContent = '—';
    });
    return;
  }
  for (const [id, cam] of Object.entries(data.cameras)) {
    document.getElementById('dot-' + id).className = 'dot ' + (cam.available ? 'on' : 'off');
    document.getElementById('stream-res-' + id).textContent = cam.resolution ?? '—';
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
      img.removeAttribute('src');
    }
  });
  if (active) redrawStreamGraphs();
}
