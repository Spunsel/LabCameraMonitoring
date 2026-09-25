const BASE    = new URL('.', window.location.href).pathname.replace(/\/$/, '');
const CAMERAS = ['whiteboard', 'robot'];
const CAM_LABEL = { whiteboard: 'whiteboard camera', robot: 'robot camera' };

// 30 min at 5 s/sample = 360 slots
const TOTAL_SLOTS = 360;

const DL_ICON_URL = new URL('icons/download.svg', document.currentScript.src).href;

// TTFB history per camera (snapshot graph)
const snapHist = {};
CAMERAS.forEach(id => snapHist[id] = []);

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

// ── Build capture columns ────────────────────────────────────────────
// capture-grid:  snapshot latency stats + graph (one col per camera)
// recent-grid:   cam label + show-last input + scrollable table
const cg = document.getElementById('capture-grid');
const rg = document.getElementById('recent-grid');
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

  // ── Recent captures table ──
  const rt = document.createElement('div');
  rt.className = 'cap-col';
  rt.innerHTML = `
    <div class="cap-col-hdr">
      <div class="cam-lbl">${CAM_LABEL[id]}</div>
      <label class="cap-limit-label">show last
        <input type="number" class="cap-limit" id="cap-limit-${id}"
               value="10" min="1" max="50">
      </label>
    </div>
    <div class="cap-tbl-wrap">
      <div class="cap-thead">
        <div class="cc cc-name">file</div>
        <div class="cc cc-date">captured</div>
        <div class="cc cc-size">size</div>
        <div class="cc cc-dl"></div>
      </div>
      <div class="cap-tbody" id="cap-body-${id}" tabindex="0"
           role="region" aria-label="${CAM_LABEL[id]} capture history">
        <div class="cap-row cap-empty">loading…</div>
      </div>
    </div>`;
  rg.appendChild(rt);
});

function updateHistoryLayout() {
  if (!document.getElementById('panel-history').classList.contains('active')) return;
  // Check the actual two-column layout, including browser zoom, font metrics,
  // and scrollbar space. Remove the stacked class before measuring so growing
  // the window can return the tables to two columns.
  rg.classList.remove('is-stacked');
  document.body.classList.remove('history-stacked');
  const clipped = [...rg.querySelectorAll('.cc-name')]
    .some(cell => cell.scrollWidth > cell.clientWidth + 1);
  rg.classList.toggle('is-stacked', clipped);
  document.body.classList.toggle('history-stacked', clipped);

  // A stacked table sizes itself to its rows, up to ten actual row heights.
  // Measure the rendered height so font and browser zoom changes stay exact.
  for (const id of CAMERAS) {
    const body = document.getElementById(`cap-body-${id}`);
    const row = body.querySelector('.cap-row:not(.cap-empty)');
    if (row) body.style.setProperty('--history-ten-rows', `${row.getBoundingClientRect().height * 10}px`);
  }
}

// ── Bar chart ────────────────────────────────────────────────────────
// maxVal is a baseline ceiling only — drawBarGraph expands it in fixed
// 25 ms steps whenever the data exceeds it, so spikes are never clipped.
const SNAP_GRAPH_OPTS = {
  maxVal:  100,
  unit:    'ms',
  colorFn: v => v < 50 ? '#4ade80' : v < 100 ? '#fbbf24' : '#f87171',
};

// Stream graph: same baseline scale — µStreamer capture-to-send latency is
// in a similar range to snapshot download time, but the two are measured
// in different places and are not directly comparable.
const STREAM_GRAPH_OPTS = {
  maxVal:  100,
  unit:    'ms',
  colorFn: v => v < 50 ? '#4ade80' : v < 100 ? '#fbbf24' : '#f87171',
};

function drawBarGraph(canvasId, values, opts) {
  const canvas = document.getElementById(canvasId);
  if (!canvas) return;
  const rect = canvas.getBoundingClientRect();
  if (rect.width === 0) return;

  const dpr = window.devicePixelRatio || 1;
  canvas.width  = Math.round(rect.width  * dpr);
  canvas.height = Math.round(rect.height * dpr);
  const ctx = canvas.getContext('2d');
  ctx.scale(dpr, dpr);

  const W = rect.width, H = rect.height;
  const PL = 28, PR = 4, PT = 4, PB = 16;
  const iW = W - PL - PR, iH = H - PT - PB;
  const { unit, colorFn } = opts;

  // Vertical scale: the ceiling still expands past opts.maxVal (the
  // baseline) in 25-unit increments whenever the data goes higher, so
  // slow requests are never clipped off the top of the chart. The label
  // step then grows in lockstep (also in 25-unit multiples) so there are
  // never more than MAX_LABELS gridlines/labels, no matter how tall the
  // chart's ceiling ends up being.
  const MAX_LABELS = 4;   // includes the "0${unit}" label at the bottom
  const dataMax = values.reduce(
    (m, v) => (v !== null && v !== undefined && v > m) ? v : m, 0);
  const rawCeil = dataMax > opts.maxVal
    ? Math.ceil(dataMax / 25) * 25
    : opts.maxVal;
  let step = 25;
  while (rawCeil / step > MAX_LABELS - 1) step += 25;
  const maxVal = Math.ceil(rawCeil / step) * step;
  const ySteps = [];
  for (let v = 0; v <= maxVal; v += step) ySteps.push(v);

  ctx.fillStyle = '#0d0d0d';
  ctx.fillRect(0, 0, W, H);

  // Y-axis gridlines + labels (v=0 carries the unit suffix, e.g. "0ms")
  ctx.font = '9px "Adwaita Mono", monospace';
  ySteps.forEach(v => {
    const y = PT + iH * (1 - v / maxVal);
    ctx.strokeStyle = '#181818'; ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(PL, y); ctx.lineTo(W - PR, y); ctx.stroke();
    ctx.fillStyle = '#6e6e6e'; ctx.textAlign = 'right';
    ctx.fillText(v === 0 ? `0${unit}` : `${v}`, PL - 3, y + 3);
  });

  // Y-axis spine
  ctx.strokeStyle = '#1e1e1e'; ctx.lineWidth = 1;
  ctx.beginPath(); ctx.moveTo(PL, PT); ctx.lineTo(PL, PT + iH); ctx.stroke();

  // Bars — fixed slot width, right-aligned; null = gap (no bar drawn)
  const barW   = iW / TOTAL_SLOTS;
  const xStart = PL + iW - values.length * barW;
  values.forEach((v, i) => {
    if (v === null || v === undefined) return;
    const barH = Math.min(v / maxVal, 1) * iH;
    ctx.fillStyle = colorFn(v);
    ctx.fillRect(xStart + i * barW, PT + iH - barH, Math.max(barW, 0.5), barH);
  });

  // Average line — dashed white with label on right (non-null values only)
  const nonNull = values.filter(v => v !== null && v !== undefined);
  if (nonNull.length > 0) {
    const avg  = nonNull.reduce((a, b) => a + b, 0) / nonNull.length;
    const avgY = PT + iH * (1 - Math.min(avg / maxVal, 1));
    ctx.strokeStyle = 'rgba(224,224,224,0.55)';
    ctx.setLineDash([3, 3]); ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(PL, avgY); ctx.lineTo(W - PR, avgY); ctx.stroke();
    ctx.setLineDash([]);
    ctx.fillStyle = 'rgba(224,224,224,0.7)'; ctx.textAlign = 'right';
    ctx.font = '9px "Adwaita Mono", monospace';
    ctx.fillText(`${Math.round(avg)}${unit}`, W - PR, avgY < PT + 10 ? avgY + 10 : avgY - 2);
  }

  // X-axis labels
  ctx.fillStyle = '#666666'; ctx.font = '9px "Adwaita Mono", monospace';
  ctx.textAlign = 'left';   ctx.fillText('−30m', PL, H - 2);
  ctx.textAlign = 'center'; ctx.fillText('−15m', PL + iW / 2, H - 2);
  ctx.textAlign = 'right';  ctx.fillText('now',  W - PR, H - 2);
}

// ── Helpers ──────────────────────────────────────────────────────────

function latCls(ms) {
  if (ms < 50)  return 'g';
  if (ms < 100) return 'w';
  return 'b';
}

function median(arr) {
  if (!arr.length) return null;
  const sorted = [...arr].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  return sorted.length % 2 !== 0 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
}

function fmtUptime(s) {
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60);
  return h > 0 ? `uptime ${h}h ${m}m` : `uptime ${m}m ${s % 60}s`;
}

function fmtDate(iso) {
  if (!iso) return '—';
  const d = new Date(iso);
  if (isNaN(d.getTime())) return iso.substring(0, 16);
  const z = n => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${z(d.getMonth()+1)}-${z(d.getDate())} ${z(d.getHours())}:${z(d.getMinutes())}`;
}

function fmtTime(d) {
  const z = n => String(n).padStart(2, '0');
  return `${z(d.getHours())}:${z(d.getMinutes())}:${z(d.getSeconds())}`;
}

// ── Snapshot download time measurement (every 5 s) ───────────────────
// fetch() resolves at headers-received (first byte). We instead record
// the time until await r.blob() completes: how long the viewer's browser
// actually waits for the whole JPEG. That is what a human perceives, and
// what differs from the stream's capture-to-send latency above.
// firstByteMs is kept only for the tooltip, not graphed.
// Failed/invalid responses push null — a gap, never a fake 0 ms.
async function measureSnapshot(id) {
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

// ── Poll camera config + availability (every 30 s) ───────────────────
// Uptime ticks every second on the client by interpolating from the last
// server value — a single setInterval touching one text node is trivial
// overhead (<<1ms/tick), far cheaper than re-polling the server every
// second just to keep a counter moving smoothly.
let uptimeBaseSeconds = null;
let uptimeBaseAt      = null;   // performance.now() when uptimeBaseSeconds was received

function tickUptime() {
  const el = document.getElementById('uptime');
  if (!el || uptimeBaseSeconds === null) return;
  const elapsed = (performance.now() - uptimeBaseAt) / 1000;
  el.textContent = fmtUptime(Math.floor(uptimeBaseSeconds + elapsed));
}

async function pollStatus() {
  let data;
  try {
    const r = await fetch(`${BASE}/api/v1/status`);
    if (!r.ok) throw new Error();
    data = await r.json();
  } catch {
    CAMERAS.forEach(id => document.getElementById(`dot-${id}`).className = 'dot off');
    return;
  }
  uptimeBaseSeconds = data.uptime_seconds;
  uptimeBaseAt      = performance.now();
  tickUptime();
  for (const [id, cam] of Object.entries(data.cameras)) {
    document.getElementById(`dot-${id}`).className = `dot ${cam.available ? 'on' : 'off'}`;
    const resEl = document.getElementById(`snap-res-${id}`);
    const fpsEl = document.getElementById(`stream-fps-${id}`);
    if (resEl) resEl.textContent = cam.resolution ?? '—';
    if (fpsEl) fpsEl.textContent = cam.fps != null ? `${cam.fps} fps` : '—';
  }
}

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

async function pollStreamMetrics() {
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

// ── Capture table rendering ────────────────────────────────────────────
function renderCaptures(captures, camId) {
  const tbody = document.getElementById(`cap-body-${camId}`);
  if (!tbody) return;
  tbody.innerHTML = '';

  if (!captures.length) {
    tbody.innerHTML = '<div class="cap-row cap-empty">no captures</div>';
    return;
  }

  for (const cap of captures) {
    const sizeBytes = cap.images?.[camId] ?? 0;
    const sizeStr   = sizeBytes ? `${(sizeBytes / 1024).toFixed(1)} kB` : '—';
    const dlUrl     = `${BASE}/api/v1/captures/${cap.event_id}/${camId}.jpg`;
    // Use the real on-disk filename (<camera>_<UTC-ts>.jpg) when available;
    // legacy captures without a "filenames" entry fall back to a constructed name.
    const filename  = cap.filenames?.[camId] ?? `${camId}-${cap.event_id}.jpg`;
    const dlCol     = sizeBytes
      ? `<a href="${dlUrl}" download="${filename}" class="dl-btn" title="Download"><img src="${DL_ICON_URL}" alt=""></a>`
      : `<span style="color:#222">—</span>`;

    const row = document.createElement('div');
    row.className = 'cap-row';
    row.innerHTML = `
      <div class="cc cc-name" title="event: ${cap.event_id}">${filename}</div>
      <div class="cc cc-date">${fmtDate(cap.captured_at)}</div>
      <div class="cc cc-size">${sizeStr}</div>
      <div class="cc cc-dl">${dlCol}</div>`;
    tbody.appendChild(row);
  }
}

// ── Poll captures (every 15 s) ─────────────────────────────────────────
async function pollCaptures() {
  let data;
  try {
    const r = await fetch(`${BASE}/api/v1/captures?limit=50`);
    if (!r.ok) throw new Error();
    data = await r.json();
  } catch { return; }

  for (const id of CAMERAS) {
    const limit = Math.min(50, Math.max(1,
      parseInt(document.getElementById(`cap-limit-${id}`).value, 10) || 10));
    renderCaptures(data.filter(c => c.images?.[id] != null).slice(0, limit), id);
  }
  updateHistoryLayout();
}

// ── Manual "capture snapshot" button (Snapshots tab) ───────────────────
// Calls the same POST /api/v1/captures endpoint used by every other
// client (CPEE included) — the timestamped filename convention is
// applied server-side in api/captures.py, not here.
async function captureSnapshot(id) {
  const btn = document.getElementById(`cap-btn-${id}`);
  if (btn) { btn.disabled = true; btn.textContent = 'capturing…'; }
  try {
    // event_id is omitted — the server auto-generates one for ad-hoc
    // captures like this. Only real callers that need to correlate a
    // capture back to something of their own (e.g. CPEE tying it to a
    // process/activity) need to supply it explicitly.
    const r = await fetch(`${BASE}/api/v1/captures`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ cameras: [id], store: true }),
    });
    if (!r.ok) throw new Error(`Capture failed: HTTP ${r.status}`);
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

// ── Tab switching (Live / Snapshots / History) ─────────────────────────
// All panels stay in the DOM the whole time — only visibility toggles.
// Chart history (snapHist/streamHist) and camera state live in module
// scope above and are never rebuilt when switching tabs.
let capturesInterval = null;

function normalizeTab(hash) {
  if (hash === '#snapshots') return 'snapshots';
  if (hash === '#history')   return 'history';
  return 'live';
}

function startCapturesPolling() {
  if (capturesInterval) return;
  capturesInterval = setInterval(pollCaptures, 15_000);
}
function stopCapturesPolling() {
  if (capturesInterval) { clearInterval(capturesInterval); capturesInterval = null; }
}

function showTab(tab) {
  document.body.classList.toggle('history-view', tab === 'history');
  if (tab !== 'history') document.body.classList.remove('history-stacked');
  document.getElementById('panel-live').classList.toggle('active', tab === 'live');
  document.getElementById('panel-snapshots').classList.toggle('active', tab === 'snapshots');
  document.getElementById('panel-history').classList.toggle('active', tab === 'history');
  document.querySelectorAll('.tab-btn').forEach(btn =>
    btn.classList.toggle('active', btn.dataset.tab === tab));

  if (tab === 'live') {
    // Reconnect MJPEG streams
    CAMERAS.forEach(id => {
      const img = document.getElementById(`stream-img-${id}`);
      if (img && !img.getAttribute('src')) img.src = img.dataset.src;
    });
    // Canvas had zero width while hidden — redraw now that it's visible
    CAMERAS.forEach(id => drawBarGraph(`graph-stream-${id}`, streamHist[id], STREAM_GRAPH_OPTS));
  } else {
    // Disconnect MJPEG streams — a merely-hidden <img> would otherwise
    // keep both stream connections open on the server indefinitely.
    CAMERAS.forEach(id => {
      const img = document.getElementById(`stream-img-${id}`);
      if (img) img.removeAttribute('src');
    });
  }

  if (tab === 'snapshots') {
    // Canvas had zero width while hidden — redraw now that it's visible
    CAMERAS.forEach(id => drawBarGraph(`graph-snap-${id}`, snapHist[id], SNAP_GRAPH_OPTS));
  }

  if (tab === 'history') {
    updateHistoryLayout();
    pollCaptures();          // fetch immediately when opening History
    startCapturesPolling();
  } else {
    stopCapturesPolling();   // only poll captures while History is visible
  }
}

window.addEventListener('hashchange', () => showTab(normalizeTab(location.hash)));

// ── Boot ─────────────────────────────────────────────────────────────
// Snapshot measurement and stream metrics run regardless of which tab is
// open, so switching tabs never creates a gap in either history.
pollStatus();
pollStreamMetrics();
Promise.all(CAMERAS.map(measureSnapshot));
showTab(normalizeTab(location.hash));   // defaults to "live"; fetches
                                         // captures too if URL is #history

setInterval(() => Promise.all(CAMERAS.map(measureSnapshot)), 5_000);
setInterval(pollStreamMetrics, 5_000);
setInterval(pollStatus,   30_000);
setInterval(tickUptime,   1_000);   // smooth per-second counter between polls
// pollCaptures is started/stopped by showTab() — only polls while the
// History tab is actually visible.

CAMERAS.forEach(id =>
  document.getElementById(`cap-limit-${id}`)
    .addEventListener('change', pollCaptures));

CAMERAS.forEach(id =>
  document.getElementById(`cap-btn-${id}`)
    .addEventListener('click', () => captureSnapshot(id)));

window.addEventListener('resize', () => {
  updateHistoryLayout();
  CAMERAS.forEach(id => {
    drawBarGraph(`graph-snap-${id}`,    snapHist[id],   SNAP_GRAPH_OPTS);
    drawBarGraph(`graph-stream-${id}`,  streamHist[id], STREAM_GRAPH_OPTS);
  });
});

// The downloaded font can change filename widths and canvas labels after
// the first paint. Recheck the layout and redraw charts once it is ready.
document.fonts.ready.then(() => {
  updateHistoryLayout();
  CAMERAS.forEach(id => {
    drawBarGraph(`graph-snap-${id}`,    snapHist[id],   SNAP_GRAPH_OPTS);
    drawBarGraph(`graph-stream-${id}`,  streamHist[id], STREAM_GRAPH_OPTS);
  });
});
