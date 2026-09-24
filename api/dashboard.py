"""HTML for the camera monitoring dashboard served at GET /dashboard."""

DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>camera-service</title>
  <style>
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

    body {
      font-family: 'SF Mono', 'Fira Code', Consolas, 'Courier New', monospace;
      font-size: 13px;
      line-height: 1.6;
      background: #0d0d0d;
      color: #c9c9c9;
      padding: 0 1.5rem 1.25rem;
    }

    .hdr {
      position: sticky;
      top: 0;
      z-index: 100;
      background: #0d0d0d;
      display: flex;
      justify-content: space-between;
      border-bottom: 1px solid #1e1e1e;
      padding: 1.25rem 0 0.4rem;
      margin-bottom: 1.25rem;
      color: #555;
    }
    .hdr-title { color: #e0e0e0; font-weight: bold; }

    .section-lbl {
      color: #e0e0e0;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      font-size: 13px;
      margin-bottom: 0.5rem;
    }

    .grid {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 1.25rem;
      margin-bottom: 1.5rem;
    }

    .cam-lbl {
      display: flex;
      align-items: center;
      gap: 0.4rem;
      color: #e0e0e0;
      font-weight: bold;
      margin-bottom: 0.4rem;
    }
    .dot     { color: #333; }
    .dot.on  { color: #4ade80; }
    .dot.off { color: #f87171; }

    .img-box {
      width: 100%;
      aspect-ratio: 16 / 9;
      background: #111;
      border: 1px solid #1e1e1e;
      overflow: hidden;
    }
    .img-box img { width: 100%; height: 100%; object-fit: cover; display: block; }

    /* Stats table + graph side by side */
    .cam-bottom {
      display: flex;
      align-items: flex-start;
      margin-top: 0.5rem;
    }
    .cam-stats {
      flex-shrink: 0;
      padding-right: 0.75rem;
      border-right: 1px solid #1e1e1e;
    }
    .cam-graph { flex: 1; min-width: 0; padding-left: 0.75rem; }
    .cam-graph canvas { width: 100%; height: 80px; display: block; }

    .mt { border-collapse: collapse; }
    .mt td { padding: 0.05rem 0; vertical-align: baseline; }
    .mt td.k { color: #555; padding-right: 0.6rem; white-space: nowrap; }

    .g { color: #4ade80; }
    .w { color: #fbbf24; }
    .b { color: #f87171; }
    .m { color: #555; }

    /* ── Capture tables ─────────────────────────────────────────────────── */

    .cap-col-hdr {
      display: flex;
      align-items: center;
      justify-content: space-between;
      margin-bottom: 0.4rem;
    }
    .cap-limit-label { color: #444; font-size: 11px; }
    .cap-limit {
      background: #111;
      border: 1px solid #1e1e1e;
      color: #888;
      font-family: inherit;
      font-size: 11px;
      width: 38px;
      padding: 1px 4px;
      text-align: center;
      -moz-appearance: textfield;
    }
    .cap-limit::-webkit-inner-spin-button,
    .cap-limit::-webkit-outer-spin-button { -webkit-appearance: none; }
    .cap-limit:focus { outline: none; border-color: #333; color: #ccc; }

    .cap-tbl-wrap { border: 1px solid #1a1a1a; }

    .cap-thead, .cap-row { display: flex; align-items: center; }
    .cap-thead { background: #111; border-bottom: 1px solid #1a1a1a; }
    .cap-tbody {
      max-height: 200px;
      overflow-y: auto;
      scrollbar-width: thin;
      scrollbar-color: #252525 #0d0d0d;
    }
    .cap-tbody::-webkit-scrollbar       { width: 5px; }
    .cap-tbody::-webkit-scrollbar-track { background: #0d0d0d; }
    .cap-tbody::-webkit-scrollbar-thumb { background: #1e1e1e; border-radius: 2px; }

    .cap-row { border-bottom: 1px solid #131313; }
    .cap-row:last-child { border-bottom: none; }
    .cap-row:hover      { background: #111; }
    .cap-row.cap-empty  { justify-content: center; padding: 0.5rem; color: #2e2e2e; font-size: 12px; }

    .cc { padding: 0.22rem 0.5rem; font-size: 12px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .cc-name { flex: 1; min-width: 0; }
    .cc-date { width: 145px; flex-shrink: 0; color: #555; }
    .cc-size { width:  85px; flex-shrink: 0; color: #444; text-align: right; }
    .cc-dl   { width:  34px; flex-shrink: 0; display: flex; align-items: center; justify-content: center; }

    .cap-thead .cc {
      color: #323232;
      font-size: 10px;
      text-transform: uppercase;
      letter-spacing: 0.06em;
      padding-top: 0.3rem;
      padding-bottom: 0.3rem;
    }

    .dl-btn {
      display: flex; align-items: center; justify-content: center;
      color: #333; text-decoration: none; transition: color 0.1s;
    }
    .dl-btn:hover { color: #999; }
    .dl-btn svg   { width: 13px; height: 13px; }
  </style>
</head>
<body>

  <div class="hdr">
    <span><span class="hdr-title">camera-service</span><span> @ lab.bpm.in.tum.de</span></span>
    <span id="uptime">—</span>
  </div>

  <div class="section-lbl">stream</div>
  <div class="grid" id="stream-grid"></div>

  <div class="section-lbl">capture metrics</div>
  <div class="grid" id="capture-grid"></div>

  <div class="section-lbl">recent captures</div>
  <div class="grid" id="recent-grid"></div>

  <script>
    const BASE    = '/cameras';
    const CAMERAS = ['whiteboard', 'robot'];
    const CAM_LABEL = { whiteboard: 'whiteboard camera', robot: 'robot camera' };

    // 30 min at 5 s/sample = 360 slots
    const TOTAL_SLOTS = 360;

    // Download icon (stroke="currentColor" → styled via CSS)
    const DL_SVG = `<svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg" fill="none"><path d="M3,12.3v7a2,2,0,0,0,2,2H19a2,2,0,0,0,2-2v-7" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" stroke-width="2"/><polyline points="7.9 12.3 12 16.3 16.1 12.3" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" stroke-width="2"/><line stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" stroke-width="2" x1="12" x2="12" y1="2.7" y2="14.2"/></svg>`;

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
          <img src="${BASE}/api/v1/cameras/${id}/stream.mjpeg" alt="${id}">
        </div>
        <div class="cam-bottom" style="margin-top:0.5rem">
          <div class="cam-stats">
            <table class="mt">
              <tr><td class="k">capture latency</td><td id="stream-lat-${id}" class="m">—</td></tr>
              <tr><td class="k">stream status</td><td id="stream-state-${id}" class="m">—</td></tr>
            </table>
          </div>
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
        <div class="cam-bottom">
          <div class="cam-stats">
            <table class="mt">
              <tr><td class="k">snapshot latency</td><td id="snap-ttfb-${id}" class="m">—</td></tr>
              <tr><td class="k">frame size</td><td id="snap-size-${id}">—</td></tr>
              <tr><td class="k">resolution</td><td id="snap-res-${id}">—</td></tr>
              <tr><td class="k">fps config</td><td id="snap-fps-${id}">—</td></tr>
            </table>
          </div>
          <div class="cam-graph">
            <canvas id="graph-snap-${id}"></canvas>
          </div>
        </div>`;
      cg.appendChild(cs);

      // ── Recent captures table ──
      const rt = document.createElement('div');
      rt.innerHTML = `
        <div class="cap-col-hdr">
          <label class="cap-limit-label">show last
            <input type="number" class="cap-limit" id="cap-limit-${id}"
                   value="10" min="1" max="50">
          </label>
        </div>
        <div class="cap-tbl-wrap">
          <div class="cap-thead">
            <div class="cc cc-name">event</div>
            <div class="cc cc-date">captured</div>
            <div class="cc cc-size">size</div>
            <div class="cc cc-dl"></div>
          </div>
          <div class="cap-tbody" id="cap-body-${id}">
            <div class="cap-row cap-empty">loading…</div>
          </div>
        </div>`;
      rg.appendChild(rt);
    });

    // ── Bar chart ────────────────────────────────────────────────────────
    const SNAP_GRAPH_OPTS = {
      maxVal:  100,
      ySteps:  [0, 25, 50, 75, 100],
      unit:    'ms',
      colorFn: v => v < 50 ? '#4ade80' : v < 100 ? '#fbbf24' : '#f87171',
    };

    // Stream graph: same scale — µStreamer capture-to-send latency is in a
    // similar range to snapshot TTFB.  Adjust thresholds after observing live data.
    const STREAM_GRAPH_OPTS = {
      maxVal:  100,
      ySteps:  [0, 25, 50, 75, 100],
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
      const { maxVal, ySteps, unit, colorFn } = opts;

      ctx.fillStyle = '#0d0d0d';
      ctx.fillRect(0, 0, W, H);

      // Y-axis gridlines + labels (v=0 carries the unit suffix, e.g. "0ms")
      ctx.font = '9px monospace';
      ySteps.forEach(v => {
        const y = PT + iH * (1 - v / maxVal);
        ctx.strokeStyle = '#181818'; ctx.lineWidth = 1;
        ctx.beginPath(); ctx.moveTo(PL, y); ctx.lineTo(W - PR, y); ctx.stroke();
        ctx.fillStyle = '#3a3a3a'; ctx.textAlign = 'right';
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
        ctx.font = '9px monospace';
        ctx.fillText(`${Math.round(avg)}${unit}`, W - PR, avgY < PT + 10 ? avgY + 10 : avgY - 2);
      }

      // X-axis labels
      ctx.fillStyle = '#303030'; ctx.font = '9px monospace';
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

    // ── Snapshot TTFB measurement (every 5 s) ────────────────────────────
    // await fetch() resolves at headers received = true TTFB.
    // Server sends Cache-Control: no-store — no cache-buster needed.
    async function measureSnapshot(id) {
      const t0 = performance.now();
      let blob, ttfb;
      try {
        const r = await fetch(`${BASE}/api/v1/cameras/${id}/snapshot.jpg`);
        ttfb = Math.round(performance.now() - t0);
        blob = await r.blob();
      } catch { return; }

      snapHist[id].push(ttfb);
      if (snapHist[id].length > TOTAL_SLOTS) snapHist[id].shift();

      const ttfbEl = document.getElementById(`snap-ttfb-${id}`);
      if (ttfbEl) { ttfbEl.textContent = `${ttfb} ms`; ttfbEl.className = latCls(ttfb); }

      const szEl = document.getElementById(`snap-size-${id}`);
      if (szEl) szEl.textContent = `${(blob.size / 1024).toFixed(1)} kB`;

      drawBarGraph(`graph-snap-${id}`, snapHist[id], SNAP_GRAPH_OPTS);
    }

    // ── Poll camera config + availability (every 30 s) ───────────────────
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
      document.getElementById('uptime').textContent = fmtUptime(data.uptime_seconds);
      for (const [id, cam] of Object.entries(data.cameras)) {
        document.getElementById(`dot-${id}`).className = `dot ${cam.available ? 'on' : 'off'}`;
        const resEl = document.getElementById(`snap-res-${id}`);
        const fpsEl = document.getElementById(`snap-fps-${id}`);
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
        const dlCol     = sizeBytes
          ? `<a href="${dlUrl}" download="${camId}-${cap.event_id}.jpg" class="dl-btn" title="Download">${DL_SVG}</a>`
          : `<span style="color:#222">—</span>`;

        const row = document.createElement('div');
        row.className = 'cap-row';
        row.innerHTML = `
          <div class="cc cc-name" title="${cap.event_id}">${cap.event_id}</div>
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
    }

    // ── Boot ─────────────────────────────────────────────────────────────
    pollStatus();
    pollCaptures();
    pollStreamMetrics();
    Promise.all(CAMERAS.map(measureSnapshot));

    setInterval(() => Promise.all(CAMERAS.map(measureSnapshot)), 5_000);
    setInterval(pollStreamMetrics, 5_000);
    setInterval(pollStatus,   30_000);
    setInterval(pollCaptures, 15_000);

    CAMERAS.forEach(id =>
      document.getElementById(`cap-limit-${id}`)
        .addEventListener('change', pollCaptures));

    window.addEventListener('resize', () =>
      CAMERAS.forEach(id => {
        drawBarGraph(`graph-snap-${id}`,    snapHist[id],   SNAP_GRAPH_OPTS);
        drawBarGraph(`graph-stream-${id}`,  streamHist[id], STREAM_GRAPH_OPTS);
      }));
  </script>
</body>
</html>"""
