import { BASE, CAMERAS } from './common.js';
import { highlightCode } from './syntax-highlight.js';

// Only supported, finite requests are offered. Live MJPEG stays on Stream.
export const OPERATIONS = [
  { id: 'snapshot', label: 'Get snapshot image', method: 'GET', camera: true, suffix: '/snapshot.jpg', help: 'Return the current JPEG without saving it on the server.' },
  { id: 'capture', label: 'Save snapshot on server', method: 'POST', camera: true, suffix: '/captures', help: 'Save a new snapshot and receive its URL. It appears in History and expires after two days.' },
  { id: 'captures', label: 'List saved captures', method: 'GET', path: '/api/v1/captures', limit: true, help: 'Return the latest saved captures across both cameras.' },
  { id: 'saved-image', label: 'Get saved image', method: 'GET', file: 'jpg', help: 'Enter a saved capture filename, for example whiteboard_20260926T184527973Z.jpg.' },
  { id: 'metadata', label: 'Get capture metadata', method: 'GET', file: 'json', help: 'Enter the capture filename with .jpg or .json; the request retrieves its JSON metadata.' },
  { id: 'controls', label: 'Read camera settings', method: 'GET', camera: true, suffix: '/controls', help: 'Read supported controls, values, ranges, and automatic-mode dependencies.' },
  { id: 'change-controls', label: 'Change camera settings', method: 'PATCH', camera: true, suffix: '/controls', key: true, body: true, help: 'Changes affect all viewers. Use native integer values from Read camera settings: exposure is in 0.1 ms; pan/tilt are in arcseconds.' },
  { id: 'reset-controls', label: 'Restore camera defaults', method: 'POST', camera: true, suffix: '/controls/reset', key: true, help: 'Restore driver defaults, including automatic modes and anti-flicker. This affects all viewers.' },
  { id: 'access', label: 'Check operator key', method: 'GET', camera: true, suffix: '/controls/access', key: true, help: 'Check whether the operator key is accepted without changing settings.' },
  { id: 'cameras', label: 'List cameras', method: 'GET', path: '/api/v1/cameras', help: 'List cameras and their snapshot and stream URLs.' },
  { id: 'status', label: 'Get service status', method: 'GET', path: '/api/v1/status', help: 'Read API uptime, camera availability, and reported resolution/FPS.' },
  { id: 'metrics', label: 'Get stream metrics', method: 'GET', path: '/api/v1/stream-metrics', help: 'Read observed stream state, FPS sample counts, and latency history.' },
  { id: 'storage', label: 'Get capture storage statistics', method: 'GET', path: '/api/v1/captures/stats', help: 'Read saved image/metadata sizes and the last successful cleanup time.' },
  { id: 'health', label: 'Check API health', method: 'GET', path: '/healthz', help: 'Check whether the API process responds.' },
  { id: 'specification', label: 'Get API specification', method: 'GET', path: '/openapi.json', help: 'Read the OpenAPI specification with endpoints, parameters, and response schemas.' },
  { id: 'ready', label: 'Check camera readiness', method: 'GET', path: '/readyz', help: 'Check whether the cameras are available.' },
];

export function buildRequest({ operation, camera, limit, filename, body }, origin = window.location.origin) {
  const op = OPERATIONS.find(item => item.id === operation);
  if (!op) throw new Error('Select an operation.');
  let path = op.path;
  if (op.camera) {
    if (!CAMERAS.includes(camera)) throw new Error('Select a camera.');
    path = `/api/v1/cameras/${encodeURIComponent(camera)}${op.suffix}`;
  }
  if (op.limit) {
    const count = Number(limit);
    if (!Number.isInteger(count) || count < 1 || count > 50) throw new Error('Capture limit must be an integer from 1 to 50.');
    path += `?limit=${count}`;
  }
  if (op.file) {
    const name = filename.trim();
    if (!/^[a-zA-Z0-9_-]+\.(jpg|json)$/.test(name)) throw new Error('Enter a capture filename ending in .jpg or .json, without a directory or URL.');
    path = `/api/v1/captures/${name.replace(/\.(jpg|json)$/, `.${op.file}`)}`;
  }
  let payload;
  if (op.body) {
    let parsed;
    try { parsed = JSON.parse(body); } catch { throw new Error('Request body must be valid JSON.'); }
    const values = parsed?.values;
    if (!values || typeof values !== 'object' || Array.isArray(values) || !Object.keys(values).length
      || Object.keys(parsed).length !== 1 || !Object.values(values).every(Number.isSafeInteger)) {
      throw new Error('Use {"values":{"control_name":integer}} with at least one control.');
    }
    payload = JSON.stringify(parsed);
  }
  return { op, method: op.method, url: new URL(`${BASE}${path}`, origin).href, body: payload };
}

export function shellQuote(value) { return `'${String(value).replaceAll("'", "'\\''")}'`; }

export function curlCommand(request) {
  const lines = ['curl --silent --show-error --include'];
  lines.push(`  --request ${request.method}`);
  if (request.op.key) lines.push('  --header "X-Camera-Control-Key: $CAMERA_CONTROLS_KEY"');
  if (request.body !== undefined) {
    lines.push("  --header 'Content-Type: application/json'");
    lines.push(`  --data-raw ${shellQuote(request.body)}`);
  }
  // Keep image bytes out of the terminal and headers out of the JPEG file.
  if (request.op.id === 'snapshot' || request.op.file === 'jpg') {
    lines[0] = 'curl --silent --show-error --dump-header -';
    lines.push("  --output 'snapshot.jpg'");
  }
  lines.push(`  ${shellQuote(request.url)}`);
  const command = lines.join(' \\\n');
  return request.op.key
    ? `read -rsp 'Operator key: ' CAMERA_CONTROLS_KEY\nprintf '\\n'\n${command}\nunset CAMERA_CONTROLS_KEY`
    : command;
}

async function copyText(text) {
  try {
    if (navigator.clipboard?.writeText) { await navigator.clipboard.writeText(text); return; }
  } catch { /* Fall back for browsers that deny clipboard access. */ }
  const input = document.createElement('textarea');
  input.value = text;
  input.style.position = 'fixed';
  input.style.opacity = '0';
  const focused = document.activeElement;
  document.body.append(input);
  input.select();
  try { if (!document.execCommand('copy')) throw new Error('Select the text and copy it manually.'); }
  finally { input.remove(); focused?.focus(); }
}

export class ApiConsole {
  constructor(host) {
    this.host = host;
    this.controller = null;
    this.imageUrl = null;
    this.responseText = '';
    this.request = null;
    this.form = host.querySelector('form');
    this.fields = this.form.elements;
    this.el = name => host.querySelector(`[data-console="${name}"]`);
    OPERATIONS.forEach(op => this.fields.operation.add(new Option(`${op.method} · ${op.label}`, op.id)));
    this.form.addEventListener('input', () => this.update());
    this.form.addEventListener('change', () => this.update());
    this.form.addEventListener('submit', event => { event.preventDefault(); this.execute(); });
    this.el('cancel').addEventListener('click', () => this.controller?.abort());
    this.el('clear-key').addEventListener('click', () => { this.fields.operatorKey.value = ''; this.update(); });
    for (const [button, content] of [['copy-url', () => this.request?.url], ['copy-curl', () => this.el('curl').textContent], ['copy-response', () => this.responseText]]) {
      const target = this.el(button);
      const icon = target.firstElementChild;
      const label = target.getAttribute('aria-label');
      let resetTimer;
      target.setAttribute('aria-live', 'polite');
      const showFeedback = success => {
        clearTimeout(resetTimer);
        target.textContent = success ? '✓' : '!';
        target.classList.toggle('copy-success', success);
        target.classList.toggle('copy-failed', !success);
        target.title = success ? 'Copied' : 'Could not copy';
        target.setAttribute('aria-label', target.title);
        resetTimer = setTimeout(() => {
          target.replaceChildren(icon);
          target.classList.remove('copy-success', 'copy-failed');
          target.title = label;
          target.setAttribute('aria-label', label);
        }, 1500);
      };
      target.addEventListener('click', async () => {
        this.el('feedback').textContent = '';
        try {
          await copyText(content() || '');
          showFeedback(true);
        } catch (error) {
          showFeedback(false);
          this.el('feedback').textContent = error.message;
        }
      });
    }
    this.update();
    window.addEventListener('pagehide', () => {
      this.controller?.abort();
      this.fields.operatorKey.value = '';
      this.releaseImage();
    });
  }

  update() {
    const op = OPERATIONS.find(item => item.id === this.fields.operation.value);
    if (!op) return;
    for (const [group, visible] of [['camera', op.camera], ['limit', op.limit], ['filename', op.file], ['body', op.body], ['key', op.key]]) {
      this.el(`${group}-field`).hidden = !visible;
    }
    this.el('help').textContent = op.help;
    this.el('feedback').textContent = '';
    try {
      this.request = buildRequest({ operation: op.id, camera: this.fields.camera.value,
        limit: this.fields.limit.value, filename: this.fields.filename.value, body: this.fields.body.value });
      this.el('url').textContent = this.request.url;
      this.el('method').textContent = this.request.method;
      highlightCode(this.el('curl'), curlCommand(this.request), 'shell');
      this.el('validation').textContent = '';
    } catch (error) {
      this.request = null;
      this.el('url').textContent = 'Complete the request fields.';
      this.el('method').textContent = op.method;
      this.el('curl').textContent = '';
      this.el('validation').textContent = error.message;
    }
    this.el('execute').disabled = !!this.controller || !this.request || (op.key && !this.fields.operatorKey.value.trim());
    this.el('copy-url').disabled = !this.request;
    this.el('copy-curl').disabled = !this.request;
  }

  releaseImage() {
    if (this.imageUrl) URL.revokeObjectURL(this.imageUrl);
    this.imageUrl = null;
    this.el('image').removeAttribute('src');
    this.el('download').removeAttribute('href');
    this.el('image-result').hidden = true;
  }

  async execute() {
    if (this.controller) return;
    this.update();
    const request = this.request;
    if (!request || (request.op.key && !this.fields.operatorKey.value.trim())) return;
    if (request.op.id === 'reset-controls' && !window.confirm(`Restore ${this.fields.camera.value} camera defaults for all viewers?`)) return;
    const controller = new AbortController();
    this.controller = controller;
    let timedOut = false;
    const timer = setTimeout(() => { timedOut = true; controller.abort(); }, 60_000);
    const started = performance.now();
    this.releaseImage();
    this.responseText = '';
    this.el('response').textContent = '';
    this.el('headers').textContent = '';
    this.el('response-request').textContent = `${request.method} ${request.url}`;
    this.el('result-link').hidden = true;
    this.el('copy-response').disabled = true;
    this.el('status').textContent = 'Sending request…';
    this.el('status').className = '';
    this.el('cancel').hidden = false;
    this.el('execute').disabled = true;
    this.form.setAttribute('aria-busy', 'true');
    try {
      const headers = {};
      if (request.body !== undefined) headers['Content-Type'] = 'application/json';
      if (request.op.key) headers['X-Camera-Control-Key'] = this.fields.operatorKey.value.trim();
      const response = await fetch(request.url, { method: request.method, headers, body: request.body,
        credentials: 'same-origin', cache: 'no-store', signal: controller.signal });
      this.el('headers').textContent = [...response.headers].map(([key, value]) => `${key}: ${value}`).join('\n');
      const blob = await response.blob();
      const elapsed = Math.round(performance.now() - started);
      this.el('status').textContent = `${response.status}${response.statusText ? ` ${response.statusText}` : ''} · ${elapsed} ms · ${blob.size.toLocaleString()} bytes`;
      this.el('status').className = response.ok ? 'g' : 'b';
      if (response.ok && blob.type.split(';')[0] === 'image/jpeg') {
        this.imageUrl = URL.createObjectURL(blob);
        this.el('image').src = this.imageUrl;
        this.el('download').href = this.imageUrl;
        this.el('image-result').hidden = false;
      } else {
        const text = await blob.text();
        let isJson = false;
        try {
          this.responseText = JSON.stringify(JSON.parse(text), null, 2);
          isJson = true;
        }
        catch { this.responseText = text; }
        if (isJson) highlightCode(this.el('response'), this.responseText, 'json');
        else this.el('response').textContent = this.responseText || '(empty response)';
        this.el('copy-response').disabled = !this.responseText;
        if (response.ok && request.op.id === 'capture') {
          const url = new URL(response.headers.get('Location') || text.trim(), request.url);
          // Only expose returned image links within this camera service.
          if (url.origin === window.location.origin && url.pathname.startsWith(`${BASE}/api/v1/captures/`)) {
            this.el('result-link').href = url.href;
            this.el('result-link').hidden = false;
          }
        }
      }
    } catch (error) {
      const message = controller.signal.aborted ? (timedOut ? 'Request timed out.' : 'Request cancelled.') : `Request failed: ${error.message}`;
      this.el('status').textContent = message + (request.method !== 'GET' ? ' The server may already have applied the request; check its state before retrying.' : '');
      this.el('status').className = 'b';
    } finally {
      clearTimeout(timer);
      this.controller = null;
      this.form.setAttribute('aria-busy', 'false');
      this.el('cancel').hidden = true;
      this.update();
    }
  }
}

const host = document.getElementById('api-console');
if (host) new ApiConsole(host);
