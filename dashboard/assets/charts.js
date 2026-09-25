import { TOTAL_SLOTS } from './common.js';

// ── Bar chart ────────────────────────────────────────────────────────
// maxVal is a baseline ceiling only — drawBarGraph expands it in fixed
// 25 ms steps whenever the data exceeds it, so spikes are never clipped.
export const SNAP_GRAPH_OPTS = {
  maxVal:  100,
  unit:    'ms',
  colorFn: v => v < 50 ? '#4ade80' : v < 100 ? '#fbbf24' : '#f87171',
};

// Stream graph: same baseline scale — µStreamer capture-to-send latency is
// in a similar range to snapshot download time, but the two are measured
// in different places and are not directly comparable.
export const STREAM_GRAPH_OPTS = {
  maxVal:  100,
  unit:    'ms',
  colorFn: v => v < 50 ? '#4ade80' : v < 100 ? '#fbbf24' : '#f87171',
};

export function drawBarGraph(canvasId, values, opts) {
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
