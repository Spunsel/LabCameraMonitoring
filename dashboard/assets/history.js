import { BASE, CAMERAS, CAM_LABEL, fmtDate } from './common.js';

const DL_ICON_URL = new URL('icons/download.svg', import.meta.url).href;
const COPY_ICON_URL = new URL('icons/copy.svg', import.meta.url).href;

const rg = document.getElementById('recent-grid');
const jpgBytesEl = document.getElementById('history-jpg-bytes');
const jsonBytesEl = document.getElementById('history-json-bytes');
const cleanupEl = document.getElementById('history-last-cleanup');

function formatBytes(bytes) {
  if (!Number.isFinite(bytes) || bytes < 0) return '—';
  if (bytes < 1024) return `${bytes} B`;
  const units = ['kB', 'MB', 'GB', 'TB'];
  let value = bytes;
  let unit = -1;
  do {
    value /= 1024;
    unit++;
  } while (value >= 1024 && unit < units.length - 1);
  return `${value.toFixed(1)} ${units[unit]}`;
}

async function pollStorageSummary() {
  try {
    const r = await fetch(`${BASE}/api/v1/captures/stats`);
    if (!r.ok) throw new Error();
    const summary = await r.json();
    jpgBytesEl.textContent = formatBytes(summary.jpg_bytes);
    jsonBytesEl.textContent = formatBytes(summary.json_bytes);
    jpgBytesEl.title = `${summary.jpg_bytes} bytes`;
    jsonBytesEl.title = `${summary.json_bytes} bytes`;
    const cleanup = summary.last_successful_cleanup;
    cleanupEl.textContent = cleanup
      ? new Date(cleanup).toLocaleString(undefined, {
          year: 'numeric', month: '2-digit', day: '2-digit',
          hour: '2-digit', minute: '2-digit', timeZoneName: 'short',
        })
      : 'never';
    cleanupEl.title = cleanup ?? '';
  } catch {
    jpgBytesEl.textContent = '—';
    jsonBytesEl.textContent = '—';
    cleanupEl.textContent = '—';
    jpgBytesEl.title = '';
    jsonBytesEl.title = '';
    cleanupEl.title = '';
  }
}

CAMERAS.forEach(id => {
  const rt = document.createElement('div');
  rt.className = 'cap-col';
  rt.innerHTML = `
    <div class="cap-col-hdr">
      <div class="cam-lbl">${CAM_LABEL[id]}</div>
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
        <div class="cc cc-copy"></div>
        <div class="cc cc-dl"></div>
      </div>
      <div class="cap-tbody" id="cap-body-${id}" tabindex="0"
           role="region" aria-label="${CAM_LABEL[id]} capture history">
        <div class="cap-row cap-empty">loading…</div>
      </div>
    </div>`;
  rg.appendChild(rt);
});

export function updateHistoryLayout() {
  if (!document.getElementById('panel-history').classList.contains('active')) return;
  rg.classList.remove('is-stacked');
  document.body.classList.remove('history-stacked');
  const shouldStack = [...rg.querySelectorAll(
    '.cc-name, .cc-date, .cc-size, .cap-thead, .cap-row:not(.cap-empty)')]
    .some(el => el.scrollWidth > el.clientWidth);
  rg.classList.toggle('is-stacked', shouldStack);
  document.body.classList.toggle('history-stacked', shouldStack);

  for (const id of CAMERAS) {
    const body = document.getElementById(`cap-body-${id}`);
    const row = body.querySelector('.cap-row:not(.cap-empty)');
    if (row) body.style.setProperty('--history-ten-rows', `${row.getBoundingClientRect().height * 10}px`);
  }
}

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
    const filename  = cap.filenames?.[camId];
    if (!filename) continue;
    const dlUrl     = `${BASE}/api/v1/captures/${encodeURIComponent(filename)}`;
    const dlCol     = sizeBytes
      ? `<a href="${dlUrl}" download="${filename}" class="dl-btn" title="Download"><img src="${DL_ICON_URL}" alt=""></a>`
      : `<span class="cc-unavailable">—</span>`;
    const copyCol   = sizeBytes
      ? `<button type="button" class="copy-btn" title="Copy link" aria-label="Copy snapshot link">
           <img src="${COPY_ICON_URL}" alt="">
         </button>`
      : `<span class="cc-unavailable">—</span>`;

    const row = document.createElement('div');
    row.className = 'cap-row';
    row.innerHTML = `
      <div class="cc cc-name" title="snapshot: ${filename}">${filename}</div>
      <div class="cc cc-date">${fmtDate(cap.captured_at)}</div>
      <div class="cc cc-size">${sizeStr}</div>
      <div class="cc cc-copy">${copyCol}</div>
      <div class="cc cc-dl">${dlCol}</div>`;
    tbody.appendChild(row);
  }
}

export async function pollCaptures() {
  pollStorageSummary();
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
  updateHistoryLayout();
}

let capturesInterval = null;

export function startHistory() {
  updateHistoryLayout();
  pollCaptures();
  if (!capturesInterval) capturesInterval = setInterval(pollCaptures, 15_000);
}

export function stopHistory() {
  if (capturesInterval) {
    clearInterval(capturesInterval);
    capturesInterval = null;
  }
}

async function copyLink(url) {
  if (navigator.clipboard?.writeText) {
    try {
      await navigator.clipboard.writeText(url);
      return;
    } catch {}
  }

  const input = document.createElement('textarea');
  input.value = url;
  input.setAttribute('readonly', '');
  input.style.position = 'fixed';
  input.style.opacity = '0';
  const previousFocus = document.activeElement;
  document.body.appendChild(input);
  input.select();
  try {
    if (!document.execCommand('copy')) throw new Error('Clipboard unavailable');
  } finally {
    input.remove();
    previousFocus?.focus({ preventScroll: true });
  }
}

function showCopyFeedback(button, success) {
  const originalIcon = button.firstElementChild;
  button.replaceChildren(success ? '✓' : '!');
  button.title = success ? 'Link copied' : 'Could not copy link';
  button.setAttribute('aria-label', button.title);
  button.classList.toggle('copy-success', success);
  button.classList.toggle('copy-failed', !success);
  setTimeout(() => {
    button.replaceChildren(originalIcon);
    button.title = 'Copy link';
    button.setAttribute('aria-label', 'Copy snapshot link');
    button.classList.remove('copy-success', 'copy-failed');
    button.disabled = false;
  }, 2_000);
}

export function bindHistoryControls() {
  CAMERAS.forEach(id =>
    document.getElementById('cap-limit-' + id)
      .addEventListener('change', pollCaptures));

  rg.addEventListener('click', async event => {
    const button = event.target.closest('.copy-btn');
    if (!button) return;
    const download = button.closest('.cap-row').querySelector('.dl-btn');
    if (!download) return;
    button.disabled = true;
    try {
      await copyLink(download.href);
      showCopyFeedback(button, true);
    } catch {
      showCopyFeedback(button, false);
    }
  });
}
