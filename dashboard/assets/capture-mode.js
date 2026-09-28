import { BASE } from './common.js';

function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

export class CaptureModePanel {
  constructor(host, cameraId, id, apply) {
    this.cameraId = cameraId;
    this.apply = apply;
    this.signature = '';
    this.data = null;
    this.editable = false;
    this.root = element('details', 'camera-controls-section camera-capture-mode');
    const summary = element('summary');
    for (const state of ['expand', 'collapse']) {
      const icon = element('img', `camera-section-${state}`);
      icon.src = `${BASE}/dashboard/assets/icons/${state}.svg`;
      icon.alt = '';
      summary.append(icon);
    }
    summary.append(element('h3', '', 'Capture mode'));
    const form = element('form');
    const grid = element('div', 'camera-controls-grid');
    for (const [key, title] of [['resolution', 'Resolution'], ['fps', 'Target FPS']]) {
      const row = element('div', 'camera-control-row');
      const label = element('label', 'camera-control-label', title);
      const input = element('select');
      input.id = `${id}-capture-${key}`;
      label.htmlFor = input.id;
      row.append(label, input);
      grid.append(row);
      this[key] = input;
    }
    this.resolution.addEventListener('change', () => { this.populateFPS(this.fps.value); this.updateButton(); });
    this.fps.addEventListener('change', () => this.updateButton());
    this.applyButton = element('button', 'cap-btn', 'apply');
    this.applyButton.type = 'submit';
    const actions = element('div', 'camera-capture-mode-actions');
    actions.append(element('small', 'camera-controls-status', 'Applies to streams and new snapshots. Briefly reconnects this camera.'), this.applyButton);
    this.status = element('p', 'camera-controls-status');
    this.status.setAttribute('role', 'status');
    this.status.setAttribute('aria-live', 'polite');
    form.append(grid, actions, this.status);
    form.addEventListener('submit', event => {
      event.preventDefault();
      if (this.applyButton.disabled) return;
      const mode = this.selected();
      if (window.confirm(`Apply ${mode.width} × ${mode.height} at ${mode.fps} FPS to ${cameraId} camera? This briefly interrupts its stream for all viewers.`)) {
        this.apply({ mode, expected: { ...this.data.current } });
      }
    });
    this.root.append(summary, form);
    host.append(this.root);
  }

  selected() {
    const [width, height] = this.resolution.value.split('x').map(Number);
    return { width, height, fps: Number(this.fps.value) };
  }

  populateFPS(preferred) {
    const mode = this.data?.modes.find(m => `${m.width}x${m.height}` === this.resolution.value);
    const rates = mode?.fps || [];
    this.fps.replaceChildren(...rates.map(rate => new Option(String(rate), String(rate))));
    this.fps.value = rates.includes(Number(preferred)) ? String(preferred) : String(rates[0] ?? '');
  }

  updateButton() {
    const current = this.data?.current;
    const selected = this.selected();
    const valid = this.data?.modes.some(m => m.width === selected.width && m.height === selected.height && m.fps.includes(selected.fps));
    this.applyButton.disabled = !this.editable || !valid || !current ||
      ['width', 'height', 'fps'].every(key => selected[key] === current[key]);
  }

  render(data, unlocked, busy, error = '') {
    this.data = data;
    const signature = JSON.stringify(data);
    if (signature !== this.signature) {
      this.signature = signature;
      const modes = data?.modes || [];
      this.resolution.replaceChildren(...modes.map(mode =>
        new Option(`${mode.width} × ${mode.height}`, `${mode.width}x${mode.height}`)));
      const current = data?.current;
      this.resolution.value = current ? `${current.width}x${current.height}` : '';
      this.populateFPS(current?.fps);
    }
    this.editable = unlocked && !busy && !!data?.write_enabled;
    this.resolution.disabled = this.fps.disabled = !this.editable;
    this.updateButton();
    this.status.textContent = error || data?.message || (!data ? 'Refresh to read capture modes.' : '');
    this.status.classList.toggle('b', !!error);
  }
}
