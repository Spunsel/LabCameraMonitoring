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
      min-height: 100vh;
      display: flex;
      flex-direction: column;
    }

    .hdr {
      position: sticky;
      top: 0;
      z-index: 100;
      background: #161616;
      display: flex;
      align-items: center;
      border-bottom: 1px solid #3a3a3a;
      /* Negative side-margins cancel the body's own horizontal padding so
         this bar's background bleeds edge-to-edge, clearly separating it
         from the page content below instead of blending into it. */
      margin: 0 -1.5rem 1.25rem;
      padding: 1rem 1.5rem 0.85rem;
      box-shadow: 0 2px 10px rgba(0, 0, 0, 0.45);
      color: #999;
      flex-shrink: 0;
    }
    .hdr-title { color: #e0e0e0; font-weight: bold; }

    /* Three independent sections. Left/right each take an equal, flexible
       share of the remaining width (flex: 1) while the tabs in the middle
       stay a fixed, natural size (flex: 0 0 auto) — so the tabs sit at the
       true center of the whole bar and never shift when the uptime text
       (right section) grows or shrinks. */
    .hdr-side {
      flex: 1 1 0%;
      min-width: 0;
      display: flex;
      align-items: center;
    }
    .hdr-right { justify-content: flex-end; }

    .section-lbl {
      color: #e0e0e0;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      font-size: 13px;
      margin-bottom: 0.5rem;
      flex-shrink: 0;
    }

    .grid {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 1.25rem;
      margin-bottom: 1.5rem;
    }
    @media (max-width: 700px) {
      .grid { grid-template-columns: 1fr; }
    }

    /* Recent-captures grid (History tab) — fills all remaining height below
       the section label; grid-auto-rows: 1fr makes the single row (or two
       stacked rows on narrow screens) stretch to that full height. */
    #recent-grid {
      flex: 1;
      min-height: 0;
      margin-bottom: 0;
      grid-auto-rows: 1fr;
    }

    .tabs {
      display: flex;
      gap: 0.5rem;
      flex: 0 0 auto;
    }
    .tab-btn {
      color: #e0e0e0;
      font-weight: bold;
      text-decoration: none;
      padding: 0.3rem 0.9rem;
      border: 1px solid #4a4a4a;
      border-radius: 3px;
      background: #1c1c1c;
      font-size: 11px;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      transition: color 0.1s, border-color 0.1s, background 0.1s;
    }
    .tab-btn:hover  { color: #fff; border-color: #666; background: #232323; }
    .tab-btn.active { color: #fff; border-color: #888; background: #2a2a2a; }

    /* Panels stay in the DOM always — visibility toggles, nothing rebuilds */
    .panel        { display: none; }
    .panel.active { display: block; }

    /* History tab grows to fill the remaining viewport height, so its
       tables reach all the way to the bottom of the browser window
       instead of being capped at a fixed pixel height. */
    #panel-history.active {
      display: flex;
      flex-direction: column;
      flex: 1;
      min-height: 0;
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
      border: 1px solid #444;
      overflow: hidden;
    }
    .img-box img { width: 100%; height: 100%; object-fit: cover; display: block; }

    /* Stats (left) + graph (right) inside one bordered container, with an
       explicit vertical divider between the two halves */
    .cam-bottom {
      display: flex;
      align-items: stretch;
      margin-top: 0.5rem;
      border: 1px solid #444;
      border-radius: 3px;
      background: #171717;
      padding: 0.6rem 0.75rem;
    }
    .cam-stats   { flex-shrink: 0; }
    .cam-divider { width: 1px; background: #444; margin: 0 0.75rem; flex-shrink: 0; }
    .cam-graph   { flex: 1; min-width: 0; }
    .cam-graph canvas { width: 100%; height: 80px; display: block; }

    .cam-lbl-row {
      display: flex;
      align-items: center;
      justify-content: space-between;
      margin-bottom: 0.4rem;
    }
    .cam-lbl-row .cam-lbl { margin-bottom: 0; }

    .cap-btn {
      background: #1c1c1c;
      border: 1px solid #4a4a4a;
      color: #e0e0e0;
      font-family: inherit;
      font-size: 11px;
      font-weight: bold;
      padding: 3px 10px;
      border-radius: 3px;
      cursor: pointer;
      transition: color 0.1s, border-color 0.1s, background 0.1s;
    }
    .cap-btn:hover:not(:disabled) { color: #fff; border-color: #777; background: #262626; }
    .cap-btn:disabled { opacity: 0.5; cursor: default; }

    .mt { border-collapse: collapse; }
    .mt td { padding: 0.05rem 0; vertical-align: baseline; }
    .mt td.k { color: #999; padding-right: 0.6rem; white-space: nowrap; }

    .g { color: #4ade80; }
    .w { color: #fbbf24; }
    .b { color: #f87171; }
    .m { color: #999; }

    /* ── Capture tables ─────────────────────────────────────────────────── */

    /* One flex column per camera — stretches to the full height of its
       (stretched) grid cell so the table wrapper below can grow into it. */
    .cap-col {
      display: flex;
      flex-direction: column;
      min-height: 0;
    }

    .cap-col-hdr {
      display: flex;
      align-items: center;
      justify-content: space-between;
      margin-bottom: 0.4rem;
      flex-shrink: 0;
    }
    .cap-limit-label { color: #888; font-size: 11px; }
    .cap-limit {
      background: #1c1c1c;
      border: 1px solid #4a4a4a;
      color: #ccc;
      font-family: inherit;
      font-size: 11px;
      width: 38px;
      padding: 1px 4px;
      text-align: center;
      -moz-appearance: textfield;
    }
    .cap-limit::-webkit-inner-spin-button,
    .cap-limit::-webkit-outer-spin-button { -webkit-appearance: none; }
    .cap-limit:focus { outline: none; border-color: #888; color: #fff; }

    /* Wrapper fills the rest of .cap-col; tbody grows inside it and scrolls
       internally once its content exceeds the available height — this is
       what makes the table reach all the way to the bottom of the window. */
    .cap-tbl-wrap {
      border: 1px solid #444;
      flex: 1;
      display: flex;
      flex-direction: column;
      min-height: 0;
    }

    .cap-thead, .cap-row { display: flex; align-items: center; }
    .cap-thead { background: #1c1c1c; border-bottom: 1px solid #444; flex-shrink: 0; }
    .cap-tbody {
      flex: 1;
      min-height: 0;
      overflow-y: auto;
      scrollbar-width: thin;
      scrollbar-color: #252525 #0d0d0d;
    }
    .cap-tbody::-webkit-scrollbar       { width: 5px; }
    .cap-tbody::-webkit-scrollbar-track { background: #0d0d0d; }
    .cap-tbody::-webkit-scrollbar-thumb { background: #1e1e1e; border-radius: 2px; }

    .cap-row { border-bottom: 1px solid #2a2a2a; }
    .cap-row:last-child { border-bottom: none; }
    .cap-row:hover      { background: #1a1a1a; }
    .cap-row.cap-empty  { justify-content: center; padding: 0.5rem; color: #2e2e2e; font-size: 12px; }

    .cc { padding: 0.22rem 0.5rem; font-size: 12px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .cc-name { flex: 1; min-width: 0; }
    .cc-date { width: 145px; flex-shrink: 0; color: #999; }
    .cc-size { width:  85px; flex-shrink: 0; color: #888; text-align: right; }
    .cc-dl   { width:  34px; flex-shrink: 0; display: flex; align-items: center; justify-content: center; }

    .cap-thead .cc {
      color: #6e6e6e;
      font-size: 10px;
      text-transform: uppercase;
      letter-spacing: 0.06em;
      padding-top: 0.3rem;
      padding-bottom: 0.3rem;
    }

    .dl-btn {
      display: flex; align-items: center; justify-content: center;
      width: 24px; height: 24px;
      color: #e0e0e0;
      background: #1c1c1c;
      border: 1px solid #4a4a4a;
      border-radius: 3px;
      text-decoration: none;
      transition: color 0.1s, border-color 0.1s, background 0.1s;
    }
    .dl-btn:hover { color: #fff; border-color: #777; background: #262626; }
    .dl-btn svg   { width: 13px; height: 13px; }
  </style>
</head>
<body>

  <div class="hdr">
    <div class="hdr-side hdr-left">
      <span><span class="hdr-title">camera-service</span><span> @ lab.bpm.in.tum.de</span></span>
    </div>
    <div class="tabs">
      <a href="#live"      class="tab-btn" data-tab="live">stream</a>
      <a href="#snapshots" class="tab-btn" data-tab="snapshots">snapshots</a>
      <a href="#history"   class="tab-btn" data-tab="history">history</a>
    </div>
    <div class="hdr-side hdr-right">
      <span id="uptime">—</span>
    </div>
  </div>

  <div class="panel" id="panel-live">
    <div class="grid" id="stream-grid"></div>
  </div>

  <div class="panel" id="panel-snapshots">
    <div class="grid" id="capture-grid"></div>
  </div>

  <div class="panel" id="panel-history">
    <div class="section-lbl">stored snapshot history, newest first</div>
    <div class="grid" id="recent-grid"></div>
  </div>

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
          <img id="stream-img-${id}" data-src="${BASE}/api/v1/cameras/${id}/stream.mjpeg"
               src="${BASE}/api/v1/cameras/${id}/stream.mjpeg" alt="${id}">
        </div>
        <div class="cam-bottom">
          <div class="cam-stats">
            <table class="mt">
              <tr><td class="k">capture-to-send latency</td><td id="stream-lat-${id}" class="m">—</td></tr>
              <tr><td class="k">stream status</td><td id="stream-state-${id}" class="m">—</td></tr>
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
              <tr><td class="k">snapshot download time</td><td id="snap-ttfb-${id}" class="m">—</td></tr>
              <tr><td class="k">frame size</td><td id="snap-size-${id}">—</td></tr>
              <tr><td class="k">resolution</td><td id="snap-res-${id}">—</td></tr>
              <tr><td class="k">fps config</td><td id="snap-fps-${id}">—</td></tr>
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
          <div class="cap-tbody" id="cap-body-${id}">
            <div class="cap-row cap-empty">loading…</div>
          </div>
        </div>`;
      rg.appendChild(rt);
    });

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
      ctx.font = '9px monospace';
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
        ctx.font = '9px monospace';
        ctx.fillText(`${Math.round(avg)}${unit}`, W - PR, avgY < PT + 10 ? avgY + 10 : avgY - 2);
      }

      // X-axis labels
      ctx.fillStyle = '#666666'; ctx.font = '9px monospace';
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
        // Use the real on-disk filename (<camera>_<UTC-ts>.jpg) when available;
        // legacy captures without a "filenames" entry fall back to a constructed name.
        const filename  = cap.filenames?.[camId] ?? `${camId}-${cap.event_id}.jpg`;
        const dlCol     = sizeBytes
          ? `<a href="${dlUrl}" download="${filename}" class="dl-btn" title="Download">${DL_SVG}</a>`
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

    window.addEventListener('resize', () =>
      CAMERAS.forEach(id => {
        drawBarGraph(`graph-snap-${id}`,    snapHist[id],   SNAP_GRAPH_OPTS);
        drawBarGraph(`graph-stream-${id}`,  streamHist[id], STREAM_GRAPH_OPTS);
      }));
  </script>
</body>
</html>"""
