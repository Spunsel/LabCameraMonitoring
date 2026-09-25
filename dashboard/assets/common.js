// Camera configuration and formatting shared across dashboard pages.
export const BASE = new URL('.', window.location.href).pathname.replace(/\/$/, '');
export const CAMERAS = ['whiteboard', 'robot'];
export const CAM_LABEL = { whiteboard: 'whiteboard camera', robot: 'robot camera' };
export const TOTAL_SLOTS = 360;

// ── Helpers ──────────────────────────────────────────────────────────

export function latCls(ms) {
  if (ms < 50)  return 'g';
  if (ms < 100) return 'w';
  return 'b';
}

export function median(arr) {
  if (!arr.length) return null;
  const sorted = [...arr].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  return sorted.length % 2 !== 0 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
}

export function fmtUptime(s) {
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60);
  return h > 0 ? `uptime ${h}h ${m}m` : `uptime ${m}m ${s % 60}s`;
}

export function fmtDate(iso) {
  if (!iso) return '—';
  const d = new Date(iso);
  if (isNaN(d.getTime())) return iso.substring(0, 16);
  const z = n => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${z(d.getMonth()+1)}-${z(d.getDate())} ${z(d.getHours())}:${z(d.getMinutes())}`;
}

export function fmtTime(d) {
  const z = n => String(n).padStart(2, '0');
  return `${z(d.getHours())}:${z(d.getMinutes())}:${z(d.getSeconds())}`;
}
