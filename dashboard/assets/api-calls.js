import { BASE } from './common.js';

export function mergeActivity(previous, data) {
  const records = new Map((data.reset ? [] : previous).map(row => [row.id, row]));
  data.records.forEach(row => records.set(row.id, row));
  return [...records.values()].sort((a, b) => b.id - a.id).slice(0, 100);
}

export class ApiCalls {
  constructor(host) {
    this.host = host;
    this.el = name => host.querySelector(`[data-calls="${name}"]`);
    this.active = false;
    this.key = '';
    this.rows = [];
    this.cursor = 0;
    this.session = '';
    this.generation = 0;
    this.el('form').addEventListener('submit', event => {
      event.preventDefault();
      const key = this.el('key').value.trim();
      if (!key) return;
      this.stop();
      this.clearRecords();
      this.key = key;
      this.el('key').value = '';
      this.el('lock').hidden = false;
      this.poll();
    });
    this.el('lock').addEventListener('click', () => this.lock());
    this.el('limit').addEventListener('change', () => this.render());
    document.addEventListener('visibilitychange', () => {
      this.stop();
      if (this.visible()) this.poll();
    });
    window.addEventListener('pagehide', () => this.lock());
  }

  visible() { return this.active && !document.hidden; }

  setActive(active) {
    this.active = active;
    this.stop();
    if (this.visible()) this.poll();
  }

  stop() {
    this.generation += 1;
    clearTimeout(this.timer);
    this.controller?.abort();
    this.controller = null;
  }

  clearRecords() {
    this.rows = [];
    this.cursor = 0;
    this.session = '';
    this.el('since').textContent = 'Activity recorded since —';
    this.el('updated').textContent = 'Last updated —';
    this.render();
  }

  lock(message = 'Enter your operator key to view API activity.') {
    this.stop();
    this.key = '';
    this.el('key').value = '';
    this.el('form').hidden = false;
    this.el('lock').hidden = true;
    this.el('status').textContent = message;
    this.clearRecords();
  }

  async poll() {
    if (!this.visible() || !this.key || this.controller) return;
    const generation = this.generation;
    const controller = new AbortController();
    this.controller = controller;
    const timeout = setTimeout(() => controller.abort(), 10000);
    const query = new URLSearchParams({ after: String(this.cursor), limit: '100' });
    if (this.session) query.set('session', this.session);
    try {
      const response = await fetch(`${BASE}/api/v1/activity?${query}`, {
        headers: { 'X-Camera-Control-Key': this.key }, cache: 'no-store',
        credentials: 'same-origin', signal: controller.signal,
      });
      if (generation !== this.generation) return;
      if (response.status === 401 || response.status === 403) {
        this.lock('Access denied. Enter a valid operator key.');
        return;
      }
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const data = await response.json();
      if (generation !== this.generation) return;
      if (data.reset) this.el('rows').replaceChildren();
      this.rows = mergeActivity(this.rows, data);
      this.cursor = data.cursor;
      this.session = data.session_id;
      this.el('form').hidden = true;
      this.el('since').textContent = `Activity recorded since ${new Date(data.started_at).toLocaleString()}`;
      this.el('updated').textContent = `Last updated ${new Date().toLocaleTimeString()}`;
      this.el('status').textContent = 'Updates every 5 seconds while this page is visible.';
      this.render();
    } catch (error) {
      if (generation === this.generation) {
        this.el('status').textContent = `Could not update activity (${error.name === 'AbortError' ? 'request timed out' : error.message}). Retrying…`;
      }
    } finally {
      clearTimeout(timeout);
      if (generation === this.generation) {
        this.controller = null;
        if (this.visible() && this.key) this.timer = setTimeout(() => this.poll(), 5000);
      }
    }
  }

  render() {
    const body = this.el('rows');
    const limit = Number(this.el('limit').value);
    const visible = this.rows.slice(0, limit);
    this.el('empty').hidden = visible.length > 0;
    this.el('empty').textContent = this.key ? 'No recent API requests recorded.' : 'Unlock to view recent API requests.';
    const existing = new Map([...body.children].map(row => [row.dataset.id, row]));
    // Retain existing nodes (and keyboard focus); only insert new or remove old rows.
    const keep = new Set(visible.map(row => String(row.id)));
    for (const [id, row] of existing) if (!keep.has(id)) row.remove();
    visible.forEach((row, index) => {
      let tr = existing.get(String(row.id));
      if (!tr) {
        tr = document.createElement('tr');
        tr.dataset.id = String(row.id);
        const cell = text => {
          const td = document.createElement('td');
          td.textContent = text;
          tr.append(td);
          return td;
        };
        const time = cell(new Date(row.time).toLocaleTimeString());
        time.title = `${new Date(row.time).toString()} · Request ID: ${row.request_id}`;
        cell(row.method).className = 'api-calls-method';
        const endpoint = cell('');
        const details = document.createElement('details');
        const summary = document.createElement('summary');
        summary.textContent = row.endpoint;
        const info = document.createElement('div');
        info.textContent = `${new Date(row.time).toString()} · Request ID: ${row.request_id}`;
        details.append(summary, info);
        endpoint.append(details);
        cell(`${row.status} ${row.status_text}`).className = row.failed ? 'b' : 'g';
        cell(`${Number(row.duration_ms).toFixed(1)} ms`).className = 'api-calls-duration';
        const result = cell(row.result);
        if (row.capture_filename && /^[A-Za-z0-9_-]{1,100}\.jpg$/.test(row.capture_filename)) {
          const link = document.createElement('a');
          link.href = `${BASE}/api/v1/captures/${encodeURIComponent(row.capture_filename)}`;
          link.textContent = row.capture_filename;
          link.target = '_blank';
          link.rel = 'noopener';
          result.replaceChildren(link);
        }
      }
      if (body.children[index] !== tr) body.insertBefore(tr, body.children[index] || null);
    });
  }
}

const host = document.getElementById('api-calls');
const page = host ? new ApiCalls(host) : null;
export function setApiCallsActive(active) { page?.setActive(active); }
