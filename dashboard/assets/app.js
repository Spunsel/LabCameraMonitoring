import { BASE, CAMERAS, fmtUptime } from './common.js';
import { pollStreamMetrics, updateStreamStatus, setStreamActive, redrawStreamGraphs } from './stream.js';
import { measureSnapshot, redrawSnapshotGraphs, bindSnapshotControls } from './snapshots.js';
import { startHistory, stopHistory, updateHistoryLayout, bindHistoryControls } from './history.js';
import { setSettingsActive } from './settings.js';
import './api-console.js';
import { setApiCallsActive } from './api-calls.js';

const API_BASE_URL = new URL('.', window.location.href).href.replace(/\/$/, '');
document.querySelectorAll('.api-docs-base').forEach(el => {
  el.textContent = API_BASE_URL;
});

document.addEventListener('camera-theme-change', () => {
  redrawStreamGraphs();
  redrawSnapshotGraphs();
});

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
    const r = await fetch(BASE + '/api/v1/status', { headers: { 'X-Camera-Background': '1' } });
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
}

function normalizeTab(hash) {
  if (hash === '#api-console' || hash === '#api') return 'api-console';
  if (hash === '#api-calls') return 'api-calls';
  if (hash === '#snapshots') return 'snapshots';
  if (hash === '#settings') return 'settings';
  if (hash === '#docs') return 'docs';
  if (hash === '#history') return 'history';
  return 'stream';
}

function showTab(tab) {
  document.body.classList.toggle('history-view', tab === 'history');
  if (tab !== 'history') document.body.classList.remove('history-stacked');
  document.getElementById('panel-stream').classList.toggle('active', tab === 'stream');
  document.getElementById('panel-snapshots').classList.toggle('active', tab === 'snapshots');
  document.getElementById('panel-api-console').classList.toggle('active', tab === 'api-console');
  document.getElementById('panel-api-calls').classList.toggle('active', tab === 'api-calls');
  setApiCallsActive(tab === 'api-calls');
  document.getElementById('panel-settings').classList.toggle('active', tab === 'settings');
  document.getElementById('panel-docs').classList.toggle('active', tab === 'docs');
  document.getElementById('panel-history').classList.toggle('active', tab === 'history');
  document.querySelectorAll('.tab-btn').forEach(btn => {
    const active = btn.dataset.tab === tab;
    btn.classList.toggle('active', active);
    if (active) btn.setAttribute('aria-current', 'page');
    else btn.removeAttribute('aria-current');
  });

  setStreamActive(tab === 'stream');
  setSettingsActive(tab === 'settings');
  if (tab === 'snapshots') redrawSnapshotGraphs();
  if (tab === 'history') startHistory();
  else stopHistory();
}

window.addEventListener('hashchange', () => showTab(normalizeTab(location.hash)));

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
