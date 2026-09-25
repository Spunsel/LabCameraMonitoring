import { BASE, CAMERAS, fmtUptime } from './common.js';
import { pollStreamMetrics, updateStreamStatus, setStreamActive, redrawStreamGraphs } from './stream.js';
import { measureSnapshot, updateSnapshotStatus, redrawSnapshotGraphs, bindSnapshotControls } from './snapshots.js';
import { startHistory, stopHistory, updateHistoryLayout, bindHistoryControls } from './history.js';

// Keep Docs examples correct both behind /cameras and on localhost.
const API_BASE_URL = new URL('.', window.location.href).href.replace(/\/$/, '');
document.querySelectorAll('.api-docs-base').forEach(el => {
  el.textContent = API_BASE_URL;
});

// Uptime ticks locally between the 30-second status requests.
let uptimeBaseSeconds = null;
let uptimeBaseAt = null;

function tickUptime() {
  const el = document.getElementById('uptime');
  if (!el || uptimeBaseSeconds === null) return;
  const elapsed = (performance.now() - uptimeBaseAt) / 1000;
  el.textContent = fmtUptime(Math.floor(uptimeBaseSeconds + elapsed));
}

async function pollStatus() {
  let data;
  try {
    const r = await fetch(BASE + '/api/v1/status');
    if (!r.ok) throw new Error();
    data = await r.json();
  } catch {
    updateStreamStatus(null);
    return;
  }
  uptimeBaseSeconds = data.uptime_seconds;
  uptimeBaseAt = performance.now();
  tickUptime();
  updateStreamStatus(data);
  updateSnapshotStatus(data);
}

function normalizeTab(hash) {
  if (hash === '#snapshots') return 'snapshots';
  if (hash === '#docs') return 'docs';
  if (hash === '#history') return 'history';
  return 'live';
}

function showTab(tab) {
  document.body.classList.toggle('history-view', tab === 'history');
  if (tab !== 'history') document.body.classList.remove('history-stacked');
  document.getElementById('panel-live').classList.toggle('active', tab === 'live');
  document.getElementById('panel-snapshots').classList.toggle('active', tab === 'snapshots');
  document.getElementById('panel-docs').classList.toggle('active', tab === 'docs');
  document.getElementById('panel-history').classList.toggle('active', tab === 'history');
  document.querySelectorAll('.tab-btn').forEach(btn =>
    btn.classList.toggle('active', btn.dataset.tab === tab));

  setStreamActive(tab === 'live');
  if (tab === 'snapshots') redrawSnapshotGraphs();
  if (tab === 'history') startHistory();
  else stopHistory();
}

window.addEventListener('hashchange', () => showTab(normalizeTab(location.hash)));

// Keep snapshot and stream samples running across tabs, but poll capture
// history only while the History tab is open.
pollStatus();
pollStreamMetrics();
Promise.all(CAMERAS.map(measureSnapshot));
showTab(normalizeTab(location.hash));

setInterval(() => Promise.all(CAMERAS.map(measureSnapshot)), 5_000);
setInterval(pollStreamMetrics, 5_000);
setInterval(pollStatus, 30_000);
setInterval(tickUptime, 1_000);

bindHistoryControls();
bindSnapshotControls();
window.addEventListener('resize', () => {
  updateHistoryLayout();
  redrawSnapshotGraphs();
  redrawStreamGraphs();
});

document.fonts.ready.then(() => {
  updateHistoryLayout();
  redrawSnapshotGraphs();
  redrawStreamGraphs();
});
