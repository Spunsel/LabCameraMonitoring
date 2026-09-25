import { BASE, CAMERAS, CAM_LABEL, TOTAL_SLOTS, latCls, median, fmtTime } from './common.js';
import { drawBarGraph, SNAP_GRAPH_OPTS } from './charts.js';
import { pollCaptures } from './history.js';

// TTFB history per camera (snapshot graph)
const snapHist = {};
CAMERAS.forEach(id => snapHist[id] = []);

// ── Snapshot page ───────────────────────────────────────────────────
const cg = document.getElementById('capture-grid');
CAMERAS.forEach(id => {
  // ── Snapshot stats + graph ──
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
          <tr><td class="k">download time</td><td id="snap-ttfb-${id}" class="m">—</td></tr>
          <tr><td class="k">frame size</td><td id="snap-size-${id}">—</td></tr>
          <tr><td class="k">resolution</td><td id="snap-res-${id}">—</td></tr>
        </table>
      </div>
      <div class="cam-divider"></div>
      <div class="cam-graph">
        <canvas id="graph-snap-${id}"></canvas>
      </div>
    </div>`;
  cg.appendChild(cs);
});

// ── Snapshot download time measurement (every 5 s) ───────────────────
// fetch() resolves at headers-received (first byte). We instead record
// the time until await r.blob() completes: how long the viewer's browser
// actually waits for the whole JPEG. That is what a human perceives, and
// what differs from the stream's capture-to-send latency above.
// firstByteMs is kept only for the tooltip, not graphed.
// Failed/invalid responses push null — a gap, never a fake 0 ms.
export async function measureSnapshot(id) {
  const t0 = performance.now();
  let downloadMs = null, firstByteMs = null, blob = null;
  try {
    const r = await fetch(`${BASE}/api/v1/cameras/${id}/snapshot.jpg`, {
      cache: 'no-store',
    });
    firstByteMs = performance.now() - t0;

    if (!r.ok || !r.headers.get('content-type')?.startsWith('image/jpeg')) {
      throw new Error(`Snapshot failed: HTTP ${r.status}`);
    }

    blob = await r.blob();
    if (!blob.size) throw new Error('Empty snapshot');

    downloadMs = performance.now() - t0;
  } catch {
    downloadMs = null;
  }

  snapHist[id].push(downloadMs);
  if (snapHist[id].length > TOTAL_SLOTS) snapHist[id].shift();

  // Big number = median of the last 5 *successful* samples — smooths
  // display noise while every individual sample still shows as its own bar.
  const last5   = snapHist[id].filter(v => v !== null).slice(-5);
  const median5 = median(last5);

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

  // Still-image preview (Snapshots tab) — reuses this same blob, so the
  // preview never triggers a second network request.
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

// ── Manual "capture snapshot" button (Snapshots tab) ───────────────────
// A bodyless POST saves one picture. The API returns the public image URL as
// plain text and in Location; the timestamped filename is chosen server-side.
export async function captureSnapshot(id) {
  const btn = document.getElementById(`cap-btn-${id}`);
  if (btn) { btn.disabled = true; btn.textContent = 'capturing…'; }
  try {
    const r = await fetch(`${BASE}/api/v1/cameras/${id}/captures`, {
      method: 'POST',
    });
    if (!r.ok) throw new Error(`Capture failed: HTTP ${r.status}`);
    if (!r.headers.get('Location')) throw new Error('Capture did not return an image URL');
    await pollCaptures();   // refresh the table immediately
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

export function updateSnapshotStatus(data) {
  for (const [id, cam] of Object.entries(data.cameras)) {
    const resEl = document.getElementById('snap-res-' + id);
    if (resEl) resEl.textContent = cam.resolution ?? '—';
  }
}

export function redrawSnapshotGraphs() {
  CAMERAS.forEach(id => drawBarGraph('graph-snap-' + id, snapHist[id], SNAP_GRAPH_OPTS));
}

export function bindSnapshotControls() {
  CAMERAS.forEach(id =>
    document.getElementById('cap-btn-' + id)
      .addEventListener('click', () => captureSnapshot(id)));
}
