import { TOTAL_SLOTS } from './common.js';

export const SNAP_GRAPH_OPTS = {
  maxVal:  100,
  unit:    'ms',
  colorFn: (v, colors) => v < 50 ? colors.good : v < 100 ? colors.warn : colors.bad,
};

export const STREAM_GRAPH_OPTS = {
  maxVal:  100,
  unit:    'ms',
  colorFn: (v, colors) => v < 50 ? colors.good : v < 100 ? colors.warn : colors.bad,
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
  const theme = getComputedStyle(document.documentElement);
  const color = key => theme.getPropertyValue(key).trim();
  const barColors = {
    good: color('--status-good'),
    warn: color('--status-warn'),
    bad: color('--status-bad'),
  };

  const MAX_LABELS = 4;
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

  ctx.fillStyle = color('--chart-bg');
  ctx.fillRect(0, 0, W, H);

  ctx.font = '9px "Adwaita Mono", monospace';
  ySteps.forEach(v => {
    const y = PT + iH * (1 - v / maxVal);
    ctx.strokeStyle = color('--chart-grid'); ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(PL, y); ctx.lineTo(W - PR, y); ctx.stroke();
    ctx.fillStyle = color('--chart-label'); ctx.textAlign = 'right';
    ctx.fillText(v === 0 ? `0${unit}` : `${v}`, PL - 3, y + 3);
  });

  ctx.strokeStyle = color('--chart-axis'); ctx.lineWidth = 1;
  ctx.beginPath(); ctx.moveTo(PL, PT); ctx.lineTo(PL, PT + iH); ctx.stroke();

  const barW   = iW / TOTAL_SLOTS;
  const xStart = PL + iW - values.length * barW;
  values.forEach((v, i) => {
    if (v === null || v === undefined) return;
    const barH = Math.min(v / maxVal, 1) * iH;
    ctx.fillStyle = colorFn(v, barColors);
    ctx.fillRect(xStart + i * barW, PT + iH - barH, Math.max(barW, 0.5), barH);
  });

  const nonNull = values.filter(v => v !== null && v !== undefined);
  if (nonNull.length > 0) {
    const avg  = nonNull.reduce((a, b) => a + b, 0) / nonNull.length;
    const avgY = PT + iH * (1 - Math.min(avg / maxVal, 1));
    ctx.strokeStyle = color('--chart-average-line');
    ctx.setLineDash([3, 3]); ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(PL, avgY); ctx.lineTo(W - PR, avgY); ctx.stroke();
    ctx.setLineDash([]);
    ctx.fillStyle = color('--chart-average-text'); ctx.textAlign = 'right';
    ctx.font = '9px "Adwaita Mono", monospace';
    ctx.fillText(`${Math.round(avg)}${unit}`, W - PR, avgY < PT + 10 ? avgY + 10 : avgY - 2);
  }

  ctx.fillStyle = color('--chart-time'); ctx.font = '9px "Adwaita Mono", monospace';
  ctx.textAlign = 'left';   ctx.fillText('−30m', PL, H - 2);
  ctx.textAlign = 'center'; ctx.fillText('−15m', PL + iW / 2, H - 2);
  ctx.textAlign = 'right';  ctx.fillText('now',  W - PR, H - 2);
}
