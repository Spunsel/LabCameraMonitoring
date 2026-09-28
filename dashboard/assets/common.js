export const BASE = new URL('.', window.location.href).pathname.replace(/\/$/, '');
export const CAMERAS = ['whiteboard', 'robot'];
export const CAM_LABEL = { whiteboard: 'whiteboard camera', robot: 'robot camera' };
export const TOTAL_SLOTS = 360;

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


// Reconnect only previews that are currently active; hidden pages stay disconnected.
export function reconnectCameraPreviews(cameraId) {
  for (const prefix of ['settings-img-', 'stream-img-']) {
    const image = document.getElementById(prefix + cameraId);
    if (image?.getAttribute('src')) {
      image.src = `${image.dataset.src}?reconnect=${Date.now()}`;
    }
  }
}

export function retryLivePreview(image) {
  let timer;
  image.addEventListener('error', () => {
    clearTimeout(timer);
    if (image.getAttribute('src')) timer = setTimeout(() => {
      if (image.getAttribute('src')) image.src = `${image.dataset.src}?reconnect=${Date.now()}`;
    }, 2000);
  });
}
