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
      padding: 1.25rem 1.5rem;
    }

    .hdr {
      display: flex;
      justify-content: space-between;
      border-bottom: 1px solid #1e1e1e;
      padding-bottom: 0.4rem;
      margin-bottom: 1.25rem;
      color: #555;
    }
    .hdr-title { color: #e0e0e0; font-weight: bold; }

    .section-lbl {
      color: #444;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      font-size: 11px;
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
      margin-bottom: 0.5rem;
    }
    .img-box img { width: 100%; height: 100%; object-fit: cover; display: block; }
    .img-box .ph {
      width: 100%; height: 100%;
      display: flex; align-items: center; justify-content: center;
      color: #333; font-size: 12px;
    }

    /* Stats + graph side by side */
    .cam-bottom {
      display: flex;
      gap: 0;
      align-items: flex-start;
    }
    .cam-stats {
      flex-shrink: 0;
      padding-right: 0.75rem;
      border-right: 1px solid #1e1e1e;
    }
    .cam-graph {
      flex: 1;
      min-width: 0;
      padding-left: 0.75rem;
    }
    .cam-graph canvas {
      width: 100%;
      height: 96px;
      display: block;
    }

    .mt { border-collapse: collapse; }
    .mt td { padding: 0.05rem 0; vertical-align: baseline; }
    .mt td.k { color: #555; padding-right: 0.6rem; white-space: nowrap; }

    .g { color: #4ade80; }
    .w { color: #fbbf24; }
    .b { color: #f87171; }
    .m { color: #555; }

    .cap-event { font-size: 11px; color: #444; margin-top: 0.3rem; }
  </style>
</head>
<body>

  <div class="hdr">
    <span><span class="hdr-title">camera-service</span><span> @ lab.bpm.in.tum.de</span></span>
    <span id="uptime">—</span>
  </div>

  <div class="section-lbl">stream</div>
  <div class="grid" id="stream-grid"></div>

  <div class="section-lbl">last capture</div>
  <div class="grid" id="capture-grid"></div>

  <script>
    const BASE    = '/cameras';
    const CAMERAS = ['whiteboard', 'robot'];

    // 1 hour at 5 s/sample = 720 slots
    // Bars are right-aligned: empty space on the left until the hour fills.
    const TOTAL_SLOTS = 720;
    const MAX_MS      = 60;   // y-axis ceiling (bars clip here)
    const THRESHOLD   = 50;   // dashed threshold line (ms)

    const hist = {};
    CAMERAS.forEach(id => hist[id] = { values: [], ts: [] });

    // ── Build stream cards ───────────────────────────────────────────────
    const sg = document.getElementById('stream-grid');
    CAMERAS.forEach(id => {
      const d = document.createElement('div');
      d.innerHTML = `
        <div class="cam-lbl"><span class="dot" id="dot-${id}">●</span>${id}</div>
        <div class="img-box">
          <img src="${BASE}/api/v1/cameras/${id}/stream.mjpeg" alt="${id}">
        </div>
        <div class="cam-bottom">
          <div class="cam-stats">
            <table class="mt">
              <tr><td class="k">latency</td><td><span id="lat-${id}" class="m">—</span></td></tr>
              <tr><td class="k">frame size</td><td id="sz-${id}">—</td></tr>
              <tr><td class="k">resolution</td><td id="res-${id}">—</td></tr>
              <tr><td class="k">fps config</td><td id="fps-${id}">—</td></tr>
            </table>
          </div>
          <div class="cam-graph">
            <canvas id="graph-${id}"></canvas>
          </div>
        </div>`;
      sg.appendChild(d);
    });

    // ── Build capture cards ──────────────────────────────────────────────
    const cg = document.getElementById('capture-grid');
    CAMERAS.forEach(id => {
      const d = document.createElement('div');
      d.id = `cap-col-${id}`;
      d.innerHTML = `
        <div class="cam-lbl">${id}</div>
        <div class="img-box"><div class="ph" id="cap-ph-${id}">no captures</div></div>
        <div class="cap-event" id="cap-lbl-${id}"></div>`;
      cg.appendChild(d);
    });

    // ── Bar chart ────────────────────────────────────────────────────────

    function lerp(a, b, t) { return Math.round(a + (b - a) * t); }

    /** Map latency (ms) → CSS colour string (green → yellow → red). */
    function barColor(ms) {
      if (ms <= 30) return '#4ade80';
      if (ms <= MAX_MS) {
        const t = (ms - 30) / 30;
        return `rgb(${lerp(74,251,t)},${lerp(222,191,t)},${lerp(128,36,t)})`;
      }
      // above ceiling: full red
      return '#f87171';
    }

    /**
     * Redraw the latency bar chart for one camera.
     * Each sample occupies (iW / TOTAL_SLOTS) px — fixed spacing regardless
     * of how many samples have been collected.  Bars grow from right to left
     * as time passes; empty space on the left = data not yet collected.
     */
    function drawGraph(id) {
      const canvas = document.getElementById(`graph-${id}`);
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

      // Background
      ctx.fillStyle = '#0d0d0d';
      ctx.fillRect(0, 0, W, H);

      // Y-axis gridlines + labels
      ctx.font = '9px monospace';
      [0, 20, 40, 60].forEach(ms => {
        const y = PT + iH * (1 - ms / MAX_MS);
        ctx.strokeStyle = '#181818';
        ctx.lineWidth = 1;
        ctx.beginPath(); ctx.moveTo(PL, y); ctx.lineTo(W - PR, y); ctx.stroke();
        ctx.fillStyle = '#3a3a3a';
        ctx.textAlign = 'right';
        ctx.fillText(`${ms}`, PL - 3, y + 3);
      });

      // "ms" unit label
      ctx.fillStyle = '#2a2a2a';
      ctx.textAlign = 'left';
      ctx.fillText('ms', 2, PT + 8);

      // Threshold dashed line
      const thY = PT + iH * (1 - THRESHOLD / MAX_MS);
      ctx.strokeStyle = '#252525';
      ctx.setLineDash([2, 3]);
      ctx.lineWidth = 1;
      ctx.beginPath(); ctx.moveTo(PL, thY); ctx.lineTo(W - PR, thY); ctx.stroke();
      ctx.setLineDash([]);

      // Y-axis spine
      ctx.strokeStyle = '#1e1e1e';
      ctx.lineWidth = 1;
      ctx.beginPath(); ctx.moveTo(PL, PT); ctx.lineTo(PL, PT + iH); ctx.stroke();

      // Bars — fixed slot width, right-aligned
      const values = hist[id].values;
      const barW   = iW / TOTAL_SLOTS;          // width of one time-slot
      const xStart = PL + iW - values.length * barW; // left edge of first bar

      values.forEach((v, i) => {
        const x    = xStart + i * barW;
        const barH = Math.min(v / MAX_MS, 1) * iH;
        ctx.fillStyle = barColor(v);
        ctx.fillRect(x, PT + iH - barH, Math.max(barW, 0.5), barH);
      });

      // X-axis labels (fixed, represent the 1-hour window)
      ctx.fillStyle = '#303030';
      ctx.font = '9px monospace';
      ctx.textAlign = 'left';
      ctx.fillText('−60m', PL, H - 2);
      ctx.textAlign = 'center';
      ctx.fillText('−30m', PL + iW / 2, H - 2);
      ctx.textAlign = 'right';
      ctx.fillText('now', W - PR, H - 2);
    }

    // ── Helpers ──────────────────────────────────────────────────────────

    function latCls(ms) {
      if (ms < 30) return 'g';
      if (ms < 80) return 'w';
      return 'b';
    }

    function fmtUptime(s) {
      const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60);
      return h > 0 ? `uptime ${h}h ${m}m` : `uptime ${m}m ${s % 60}s`;
    }

    // ── Client-side latency measurement ──────────────────────────────────
    // Fetches a real snapshot; measures full round-trip with performance.now().
    // Also reads blob.size for frame size — no extra requests needed.
    async function measureLatency(id) {
      const t0 = performance.now();
      let blob, ms;
      try {
        const r = await fetch(`${BASE}/api/v1/cameras/${id}/snapshot.jpg?t=${Date.now()}`);
        blob = await r.blob();
        ms   = Math.round(performance.now() - t0);
      } catch {
        return;
      }

      const h = hist[id];
      h.values.push(ms);
      h.ts.push(Date.now());
      if (h.values.length > TOTAL_SLOTS) { h.values.shift(); h.ts.shift(); }

      const latEl = document.getElementById(`lat-${id}`);
      latEl.textContent = `${ms} ms`;
      latEl.className   = latCls(ms);

      document.getElementById(`sz-${id}`).textContent =
        `${(blob.size / 1024).toFixed(1)} kB`;

      drawGraph(id);
    }

    // ── Poll camera config + availability (cheap; infrequent) ────────────
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
        document.getElementById(`res-${id}`).textContent = cam.resolution ?? '—';
        document.getElementById(`fps-${id}`).textContent =
          cam.fps != null ? `${cam.fps} fps` : '—';
      }
    }

    // ── Poll latest capture (read-only) ───────────────────────────────────
    async function pollCaptures() {
      let ids;
      try {
        const r = await fetch(`${BASE}/api/v1/captures`);
        if (!r.ok) throw new Error();
        ids = await r.json();
      } catch { return; }

      if (!ids.length) return;
      const latest = ids[0];

      CAMERAS.forEach(id => {
        const box = document.getElementById(`cap-ph-${id}`).parentElement;
        const lbl = document.getElementById(`cap-lbl-${id}`);

        let img = box.querySelector('img');
        if (!img) {
          img = document.createElement('img');
          img.alt    = `${id} capture`;
          img.onload  = () => { const ph = box.querySelector('.ph'); if (ph) ph.style.display = 'none'; };
          img.onerror = () => {
            img.style.display = 'none';
            const ph = box.querySelector('.ph');
            if (ph) { ph.textContent = 'no image'; ph.style.display = 'flex'; }
          };
          box.appendChild(img);
        }
        img.style.display = '';
        img.src = `${BASE}/api/v1/captures/${latest}/${id}.jpg?t=${Date.now()}`;
        lbl.textContent = latest;
      });
    }

    // ── Boot ─────────────────────────────────────────────────────────────
    pollStatus();
    pollCaptures();
    CAMERAS.forEach(measureLatency);

    // Config rarely changes — poll every 30 s
    setInterval(pollStatus,   30_000);
    // Latency: every 5 s per camera
    setInterval(() => CAMERAS.forEach(measureLatency), 5_000);
    // Captures: every 15 s
    setInterval(pollCaptures, 15_000);

    // Redraw on resize (canvas dimensions are pixel-exact, must be reset)
    window.addEventListener('resize', () => CAMERAS.forEach(drawGraph));
  </script>
</body>
</html>"""
