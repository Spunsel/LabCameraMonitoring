import { BASE, CAMERAS, CAM_LABEL, TOTAL_SLOTS, latCls, median, fmtTime } from './common.js';
import { drawBarGraph, SNAP_GRAPH_OPTS } from './charts.js';
import { pollCaptures } from './history.js';
import { buildTimeline } from './timeline.js';

const snapHist = {};
const firstByteHist = {};
const samples = {};
CAMERAS.forEach(id => {
  samples[id] = [];
  snapHist[id] = [];
  firstByteHist[id] = [];
});

const cg = document.getElementById('capture-grid');
CAMERAS.forEach(id => {
  const cs = document.createElement('div');
  cs.innerHTML = `
    <div class="cam-lbl-row">
      <div class="cam-lbl">${CAM_LABEL[id]}</div>
      <button type="button" class="cap-btn" id="cap-btn-${id}">capture snapshot</button>
    </div>
    <div class="img-box">
      <img id="snap-img-${id}" alt="${id} snapshot">
    </div>
    <div class="cam-bottom">
      <div class="cam-stats">
        <table class="mt">
          <tr><td class="k">last refresh</td><td id="snap-refresh-${id}" class="m">—</td></tr>
          <tr><td class="k">time to first byte</td><td id="snap-firstbyte-${id}" class="m">—</td></tr>
          <tr><td class="k">download time</td><td id="snap-ttfb-${id}" class="m">—</td></tr>
          <tr><td class="k">frame size</td><td id="snap-size-${id}">—</td></tr>
        </table>
      </div>
      <div class="cam-divider"></div>
      <div class="cam-graph">
        <canvas id="graph-snap-${id}"></canvas>
      </div>
    </div>`;
  cg.appendChild(cs);
});

export async function measureSnapshot(id, signal) {
  const t0 = performance.now();
  let downloadMs = null, firstByteMs = null, blob = null;
  try {
    const r = await fetch(`${BASE}/api/v1/cameras/${id}/snapshot.jpg`, {
      signal,
      cache: 'no-store',
      headers: { 'X-Camera-Background': '1' },
    });
    firstByteMs = performance.now() - t0;

    if (!r.ok || !r.headers.get('content-type')?.startsWith('image/jpeg')) {
      throw new Error(`Snapshot failed: HTTP ${r.status}`);
    }

    blob = await r.blob();
    if (!blob.size) throw new Error('Empty snapshot');

    downloadMs = performance.now() - t0;
  } catch {
    if (signal?.aborted) return;
    downloadMs = null;
    firstByteMs = null;
  }

  if (signal?.aborted) return;

  const now = Date.now();
  samples[id].push({ timestamp: now, downloadMs, firstByteMs });
  samples[id] = samples[id].filter(sample => sample.timestamp > now - TOTAL_SLOTS * 5000)
    .slice(-TOTAL_SLOTS);
  snapHist[id] = buildTimeline(samples[id], 'downloadMs', now, TOTAL_SLOTS);
  firstByteHist[id] = buildTimeline(samples[id], 'firstByteMs', now, TOTAL_SLOTS);

  const last5   = snapHist[id].filter(v => v !== null).slice(-5);
  const median5 = median(last5);
  const firstByte5 = median(firstByteHist[id].filter(v => v !== null).slice(-5));

  const firstByteEl = document.getElementById(`snap-firstbyte-${id}`);
  if (firstByteEl) {
    if (firstByte5 !== null) {
      const rounded = Math.round(firstByte5);
      firstByteEl.textContent = `${rounded} ms`;
      firstByteEl.className = latCls(rounded);
      firstByteEl.title = 'Median of the last 5 successful snapshot requests';
    } else {
      firstByteEl.textContent = '—';
      firstByteEl.className = 'm';
      firstByteEl.title = '';
    }
  }

  const ttfbEl = document.getElementById(`snap-ttfb-${id}`);
  if (ttfbEl) {
    if (median5 !== null) {
      const rounded = Math.round(median5);
      ttfbEl.textContent = `${rounded} ms`;
      ttfbEl.className   = latCls(rounded);
      ttfbEl.title = firstByteMs !== null
        ? `median of last 5 samples — latest: first byte ${Math.round(firstByteMs)} ms, full download ${downloadMs !== null ? Math.round(downloadMs) : '—'} ms`
        : '';
    } else {
      ttfbEl.textContent = '—';
      ttfbEl.className   = 'm';
      ttfbEl.title = '';
    }
  }

  const szEl = document.getElementById(`snap-size-${id}`);
  if (szEl) szEl.textContent = blob ? `${(blob.size / 1024).toFixed(1)} kB` : '—';

  if (blob) {
    const imgEl = document.getElementById(`snap-img-${id}`);
    if (imgEl) {
      const url = URL.createObjectURL(blob);
      const old = imgEl.dataset.url;
      imgEl.src = url;
      imgEl.dataset.url = url;
      if (old) URL.revokeObjectURL(old);
    }
    const refreshEl = document.getElementById(`snap-refresh-${id}`);
    if (refreshEl) refreshEl.textContent = fmtTime(new Date());
  }

  drawBarGraph(`graph-snap-${id}`, snapHist[id], SNAP_GRAPH_OPTS);
}

export async function captureSnapshot(id) {
  const btn = document.getElementById(`cap-btn-${id}`);
  if (btn) { btn.disabled = true; btn.textContent = 'capturing…'; }
  try {
    const r = await fetch(`${BASE}/api/v1/cameras/${id}/captures`, {
      method: 'POST',
    });
    if (!r.ok) throw new Error(`Capture failed: HTTP ${r.status}`);
    if (!r.headers.get('Location')) throw new Error('Capture did not return an image URL');
    await pollCaptures();
    if (btn) btn.textContent = 'captured ✓';
  } catch (err) {
    if (btn) btn.textContent = 'failed';
    console.error(err);
  } finally {
    setTimeout(() => {
      if (btn) { btn.disabled = false; btn.textContent = 'capture snapshot'; }
    }, 1500);
  }
}

export function redrawSnapshotGraphs() {
  CAMERAS.forEach(id => {
    snapHist[id] = buildTimeline(samples[id], 'downloadMs', Date.now(), TOTAL_SLOTS);
    drawBarGraph('graph-snap-' + id, snapHist[id], SNAP_GRAPH_OPTS);
  });
}

export function bindSnapshotControls() {
  CAMERAS.forEach(id =>
    document.getElementById('cap-btn-' + id)
      .addEventListener('click', () => captureSnapshot(id)));
}
