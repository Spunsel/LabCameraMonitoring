import { BASE, CAMERAS, fmtUptime } from './common.js';
import { pollStreamMetrics, updateStreamStatus, setStreamActive, redrawStreamGraphs } from './stream.js';
import { measureSnapshot, redrawSnapshotGraphs, bindSnapshotControls } from './snapshots.js';
import { startHistory, stopHistory, updateHistoryLayout, bindHistoryControls } from './history.js';
import { setSettingsActive } from './settings.js';
import './api-console.js';
import { setApiCallsActive } from './api-calls.js';
import { createPoller } from './polling.js';

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

async function pollStatus(signal) {
  let data;
  try {
    const r = await fetch(BASE + '/api/v1/status', { signal, headers: { 'X-Camera-Background': '1' } });
    if (!r.ok) throw new Error();
    data = await r.json();
  } catch {
    if (signal.aborted) return;
    updateStreamStatus(null);
    return;
  }
  if (signal.aborted) return;
  uptimeBaseSeconds = data.uptime_seconds;
  uptimeBaseAt = performance.now();
  tickUptime();
  updateStreamStatus(data);
}

let selectedTab = 'stream';
const statusPoller = createPoller(pollStatus, 30_000);
const metricsPoller = createPoller(pollStreamMetrics, 5_000);
const snapshotsPoller = createPoller(
  signal => Promise.all(CAMERAS.map(id => measureSnapshot(id, signal))), 5_000
);

function updateActivity() {
  const visible = !document.hidden;
  const stream = visible && selectedTab === 'stream';
  setStreamActive(stream);
  setSettingsActive(visible && selectedTab === 'settings');
  statusPoller[visible ? 'start' : 'stop']();
  metricsPoller[stream ? 'start' : 'stop']();
  // Keep snapshot measurements running across dashboard tabs and visibility changes.
  snapshotsPoller.start();
  if (visible && selectedTab === 'history') startHistory();
  else stopHistory();
  setApiCallsActive(visible && selectedTab === 'api-calls');
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
  selectedTab = tab;
  document.body.classList.toggle('history-view', tab === 'history');
  if (tab !== 'history') document.body.classList.remove('history-stacked');
  document.getElementById('panel-stream').classList.toggle('active', tab === 'stream');
  document.getElementById('panel-snapshots').classList.toggle('active', tab === 'snapshots');
  document.getElementById('panel-api-console').classList.toggle('active', tab === 'api-console');
  document.getElementById('panel-api-calls').classList.toggle('active', tab === 'api-calls');
  document.getElementById('panel-settings').classList.toggle('active', tab === 'settings');
  document.getElementById('panel-docs').classList.toggle('active', tab === 'docs');
  document.getElementById('panel-history').classList.toggle('active', tab === 'history');
  document.querySelectorAll('.tab-btn').forEach(btn => {
    const active = btn.dataset.tab === tab;
    btn.classList.toggle('active', active);
    if (active) btn.setAttribute('aria-current', 'page');
    else btn.removeAttribute('aria-current');
  });

  if (tab === 'snapshots') redrawSnapshotGraphs();
  updateActivity();
}

window.addEventListener('hashchange', () => showTab(normalizeTab(location.hash)));

showTab(normalizeTab(location.hash));

setInterval(() => { if (!document.hidden) tickUptime(); }, 1_000);
document.addEventListener('visibilitychange', updateActivity);
window.addEventListener('pagehide', () => {
  statusPoller.stop();
  metricsPoller.stop();
  snapshotsPoller.stop();
  stopHistory();
  setStreamActive(false);
  setSettingsActive(false);
  setApiCallsActive(false);
});
window.addEventListener('pageshow', updateActivity);

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
