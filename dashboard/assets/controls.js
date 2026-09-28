import { BASE } from './common.js';

// One model per camera, with operator access shared across the Settings page.
const models = new Map();
const accessPanels = new Set();
let operatorKey = ''; // Memory only; never saved in browser storage or URLs.
let panelSequence = 0;

async function request(cameraId, suffix = '', options = {}, key = operatorKey) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 60_000);
  try {
    const response = await fetch(`${BASE}/api/v1/cameras/${encodeURIComponent(cameraId)}/controls${suffix}`, {
      ...options, cache: 'no-store', signal: controller.signal,
      headers: {
        ...(options.body ? { 'Content-Type': 'application/json' } : {}),
        ...(key ? { 'X-Camera-Control-Key': key } : {}),
      },
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      const detail = data.detail;
      const error = new Error(typeof detail === 'string' ? detail
        : detail?.message || `Request failed (HTTP ${response.status}). Refresh settings and try again.`);
      error.state = detail?.state;
      error.status = response.status;
      throw error;
    }
    return data;
  } catch (error) {
    if (error.name === 'AbortError') {
      throw new Error('Request timed out. Refresh to check which settings were applied.');
    }
    throw error;
  } finally {
    clearTimeout(timer);
  }
}

function updateAllPanels() {
  models.forEach(model => model.notify());
  accessPanels.forEach(panel => panel.render());
}

class CameraControlState {
  constructor(cameraId) {
    this.cameraId = cameraId;
    this.panels = new Set();
    this.data = null;
    this.busy = false;
    this.message = '';
    this.error = false;
    this.configs = [];
    this.undoToken = '';
    this.undoRevision = '';
  }

  notify() { this.panels.forEach(panel => panel.render()); }

  accept(data) {
    this.data = data;
    if (data?.undo_token) {
      this.undoToken = data.undo_token;
      this.undoRevision = data.revision;
    } else if (!data || data.revision !== this.undoRevision) {
      this.undoToken = '';
      this.undoRevision = '';
    }
    if (data?.configs) this.configs = data.configs;
  }

  async perform(suffix = '', options = {}) {
    if (this.busy) return false;
    this.busy = true;
    this.error = false;
    this.message = suffix === '/configs' ? 'Saving configuration…'
      : options.method ? 'Applying settings…' : 'Reading camera settings…';
    updateAllPanels();
    try {
      this.accept(await request(this.cameraId, suffix, options));
      if (!options.method && operatorKey) {
        this.configs = (await request(this.cameraId, '/configs')).configs;
      }
      this.message = this.data.message || (this.data.controls.length ? '' : 'No supported controls reported.');
      return true;
    } catch (error) {
      if (error.status === 403) operatorKey = '';
      // Saving a name cannot change the camera or consume its undo slot.
      if (suffix !== '/configs') this.accept(error.state || null);
      // A failed write may have partly succeeded. Read actual state before re-enabling inputs.
      if (options.method && !this.data) {
        try { this.accept(await request(this.cameraId)); } catch {}
      }
      this.error = true;
      this.message = error.message;
      return false;
    } finally {
      this.busy = false;
      updateAllPanels();
    }
  }
}

function element(tag, className, text) {
  const el = document.createElement(tag);
  if (className) el.className = className;
  if (text !== undefined) el.textContent = text;
  return el;
}

function displayUnits(name) {
  if (name === 'exposure_time_absolute') return { scale: 10, suffix: 'ms' };
  if (name === 'pan_absolute' || name === 'tilt_absolute') return { scale: 3600, suffix: '°' };
  if (name === 'white_balance_temperature') return { scale: 1, suffix: 'K' };
  return { scale: 1, suffix: '' };
}

const CONTROL_SECTIONS = [
  ['Focus & exposure', ['focus_absolute', 'focus_automatic_continuous', 'exposure_time_absolute', 'auto_exposure']],
  ['Framing', ['zoom_absolute', 'pan_absolute', 'tilt_absolute']],
  ['Image tuning', ['white_balance_temperature', 'white_balance_automatic', 'gain', 'brightness', 'contrast', 'saturation', 'sharpness']],
  ['Lighting & frame rate', ['power_line_frequency', 'backlight_compensation', 'exposure_dynamic_framerate']],
];
const AUTO_CONTROLS = {
  focus_absolute: 'focus_automatic_continuous',
  exposure_time_absolute: 'auto_exposure',
  white_balance_temperature: 'white_balance_automatic',
};
const FULL_WIDTH = new Set(['zoom_absolute', 'power_line_frequency']);

export class CameraControlsAccess {
  constructor(host) {
    this.authBusy = false;
    this.error = '';
    accessPanels.add(this);
    this.root = element('div', 'camera-settings-access');
    const heading = element('div', 'camera-settings-title');
    this.mode = element('span', 'camera-settings-mode');
    this.modeIcon = element('span', 'camera-settings-mode-icon');
    this.modeIcon.setAttribute('aria-hidden', 'true');
    this.modeText = element('span');
    this.mode.append(this.modeIcon, this.modeText);
    this.mode.setAttribute('role', 'status');
    this.mode.setAttribute('aria-live', 'polite');
    this.mode.setAttribute('aria-atomic', 'true');
    heading.append(element('strong', '', 'Camera settings'), this.mode);
    this.root.append(heading);
    this.accessForm = element('form', 'camera-controls-access');
    const label = element('label', '', 'Operator key');
    label.htmlFor = 'camera-controls-operator-key';
    this.keyInput = element('input');
    this.keyInput.id = label.htmlFor;
    this.keyInput.type = 'password';
    this.keyInput.autocomplete = 'off';
    this.keyInput.maxLength = 512;
    this.keyInput.required = true;
    this.keyInput.placeholder = 'Enter to enable changes';
    this.unlockButton = element('button', 'cap-btn', 'unlock controls');
    this.unlockButton.type = 'submit';
    this.accessForm.append(label, this.keyInput, this.unlockButton);
    this.accessForm.addEventListener('submit', event => {
      event.preventDefault();
      this.unlock();
    });
    this.lockButton = element('button', 'cap-btn', 'lock controls');
    this.lockButton.type = 'button';
    this.lockButton.addEventListener('click', () => {
      operatorKey = '';
      models.forEach(model => { model.configs = []; model.undoToken = ''; });
      this.error = '';
      updateAllPanels();
    });
    this.status = element('p', 'camera-controls-status');
    this.status.setAttribute('role', 'status');
    this.status.setAttribute('aria-live', 'polite');
    this.root.append(this.accessForm, this.status, this.lockButton);
    host.append(this.root);
    this.render();
  }

  async unlock() {
    const camera = [...models.values()].find(model => model.data?.write_enabled);
    if (this.authBusy || !camera) return;
    this.authBusy = true;
    this.error = '';
    const key = this.keyInput.value.trim();
    this.keyInput.value = '';
    this.render();
    try {
      await request(camera.cameraId, '/access', {}, key);
      operatorKey = key;
      await Promise.all([...models.values()].map(model => model.perform()));
    } catch (error) {
      this.error = error.message;
    } finally {
      this.authBusy = false;
      updateAllPanels();
    }
  }

  render() {
    const available = [...models.values()].some(model => model.data?.write_enabled);
    const loading = [...models.values()].some(model => model.busy);
    this.accessForm.hidden = !!operatorKey || !available;
    this.keyInput.disabled = this.authBusy;
    this.unlockButton.disabled = this.authBusy;
    this.lockButton.hidden = !operatorKey;
    this.lockButton.disabled = this.authBusy;
    this.root.classList.toggle('is-locked', !operatorKey);
    const editing = !!operatorKey && available;
    this.modeText.textContent = editing ? 'Edit mode' : 'View mode';
    this.mode.dataset.mode = editing ? 'edit' : 'view';
    this.status.textContent = this.error || (this.authBusy ? 'Checking operator key…'
      : available ? ''
      : loading ? 'Reading camera settings…' : 'Operator access is unavailable. Refresh a camera to try again.');
    this.status.classList.toggle('b', !!this.error);
  }
}

// Native dialogs provide focus trapping, Escape and focus restoration.
class CameraConfigDialog {
  constructor(panel, config = null) {
    this.panel = panel;
    this.config = config;
    this.busy = false;
    this.root = element('dialog', 'camera-config-dialog');
    this.form = element('form');
    const title = element('h2', '', config ? 'Switch configuration' : 'Save configuration');
    title.id = `${panel.id}-dialog-title`;
    this.root.setAttribute('aria-labelledby', title.id);
    const camera = panel.model.cameraId;
    this.form.append(title, element('p', '', config
      ? `Are you sure you want to switch configuration for ${camera} camera to “${config.name}”?`
      : `Save the current settings for ${camera} camera.`));
    if (!config) {
      const label = element('label', '', 'Configuration name');
      this.input = element('input');
      this.input.id = `${panel.id}-config-name`;
      label.htmlFor = this.input.id;
      this.input.type = 'text';
      this.input.required = true;
      this.input.maxLength = 80;
      this.input.autocomplete = 'off';
      this.input.autofocus = true;
      this.form.append(label, this.input);
    }
    this.error = element('p', 'camera-controls-status b');
    this.error.setAttribute('role', 'alert');
    const actions = element('div', 'camera-config-dialog-actions');
    this.cancel = element('button', 'cap-btn', config ? 'abort' : 'discard');
    this.cancel.type = 'button';
    this.cancel.addEventListener('click', () => this.root.close());
    this.submit = element('button', 'cap-btn', config ? 'switch' : 'save');
    this.submit.type = 'submit';
    actions.append(this.cancel, this.submit);
    this.form.append(this.error, actions);
    this.form.addEventListener('submit', event => { event.preventDefault(); this.save(); });
    this.root.addEventListener('cancel', event => { if (this.busy) event.preventDefault(); });
    this.root.addEventListener('close', () => { this.root.remove(); panel.dialog = null; });
    this.root.append(this.form);
    document.body.append(this.root);
    this.root.showModal();
    (this.input || this.cancel).focus();
  }

  async save() {
    if (this.busy || this.panel.model.busy) return;
    if (!operatorKey) { this.error.textContent = 'Unlock controls before continuing.'; return; }
    const name = this.input?.value.trim();
    if (this.input && (!name || !this.input.checkValidity())) {
      this.error.textContent = 'Enter a configuration name (up to 80 characters).';
      this.input.focus();
      return;
    }
    this.busy = true;
    this.cancel.disabled = this.submit.disabled = true;
    if (this.input) this.input.disabled = true;
    this.error.textContent = '';
    const ok = await this.panel.model.perform(this.config
      ? `/configs/${encodeURIComponent(this.config.id)}/load` : '/configs', {
      method: 'POST', ...(this.config ? {} : { body: JSON.stringify({ name }) }),
    });
    this.busy = false;
    if (ok) this.root.close();
    else {
      this.error.textContent = this.panel.model.message;
      this.cancel.disabled = this.submit.disabled = false;
      if (this.input) { this.input.disabled = false; this.input.focus(); }
    }
  }
}

export class CameraControlsPanel {
  constructor(host, cameraId, actionsHost = null) {
    if (!models.has(cameraId)) models.set(cameraId, new CameraControlState(cameraId));
    this.model = models.get(cameraId);
    this.model.panels.add(this);
    this.id = `camera-settings-${++panelSequence}`;
    this.rows = new Map();
    this.signature = '';

    this.root = element('div', 'camera-controls');
    this.root.dataset.cameraId = cameraId;
    this.sections = element('div', 'camera-controls-sections');
    this.refreshButton = element('button', 'cap-btn camera-settings-refresh');
    const refreshIcon = element('img');
    refreshIcon.src = `${BASE}/dashboard/assets/icons/refresh.svg`;
    refreshIcon.alt = '';
    this.refreshButton.append(refreshIcon, element('span', '', 'refresh'));
    this.refreshButton.setAttribute('aria-label', `Refresh ${cameraId} settings`);
    this.refreshButton.type = 'button';
    this.refreshButton.addEventListener('click', () => this.model.perform());
    (actionsHost || this.root).append(this.refreshButton);
    this.resetButton = element('button', 'cap-btn', 'restore defaults');
    this.resetButton.type = 'button';
    this.resetButton.addEventListener('click', () => {
      if (window.confirm(`Restore ${cameraId} camera defaults, including automatic modes and anti-flicker? This changes the feed for all viewers.`)) {
        this.model.perform('/reset', { method: 'POST' });
      }
    });
    this.status = element('p', 'camera-controls-status');
    this.status.setAttribute('role', 'status');
    this.status.setAttribute('aria-live', 'polite');
    this.saveButton = element('button', 'cap-btn', 'save config');
    this.saveButton.type = 'button';
    this.saveButton.addEventListener('click', () => {
      if (!this.dialog) this.dialog = new CameraConfigDialog(this);
    });
    this.loadSelect = element('select', 'camera-config-select');
    this.loadSelect.setAttribute('aria-label', `Load configuration for ${cameraId} camera`);
    this.loadSelect.addEventListener('change', () => {
      const config = this.model.configs.find(c => c.id === this.loadSelect.value);
      this.loadSelect.value = '';
      if (config && !this.dialog) this.dialog = new CameraConfigDialog(this, config);
    });
    this.undoButton = element('button', 'cap-btn camera-controls-undo');
    this.undoButton.type = 'button';
    this.undoButton.setAttribute('aria-label', `Undo last change to ${cameraId} camera`);
    const undoIcon = element('span', 'camera-controls-undo-icon');
    undoIcon.setAttribute('aria-hidden', 'true');
    this.undoButton.append(undoIcon);
    this.undoButton.addEventListener('click', () => {
      if (this.model.undoToken) this.model.perform('/undo', {
        method: 'POST', body: JSON.stringify({ undo_token: this.model.undoToken }),
      });
    });
    const footer = element('div', 'camera-controls-footer');
    const configs = element('div', 'camera-controls-config-actions');
    configs.append(this.saveButton, this.loadSelect);
    const restore = element('div', 'camera-controls-restore-actions');
    restore.append(this.resetButton, this.undoButton);
    footer.append(configs, restore, this.status);
    this.root.append(this.sections);
    this.root.append(footer);
    host.append(this.root);
    this.render();
  }

  addControl(control) {
    const row = element('div', 'camera-control-row');
    const label = element('label', 'camera-control-label', control.label);
    label.htmlFor = `${this.id}-${control.name}`;
    const header = element('div', 'camera-control-header');
    header.append(label);
    const inputs = element('div', 'camera-control-inputs');
    const units = displayUnits(control.name);
    let input, slider;
    const exposureToggle = control.name === 'auto_exposure' && control.type === 'menu'
      && control.menu.length === 2 && [1, 3].every(value => control.menu.some(item => item.value === value));
    const toggleValues = exposureToggle ? { on: 3, off: 1 } : { on: 1, off: 0 };
    const isToggle = exposureToggle || control.type === 'bool' || (control.name === 'backlight_compensation'
      && control.min === 0 && control.max === 1);
    if (isToggle) {
      input = element('input');
      input.type = 'checkbox';
      input.setAttribute('role', 'switch');
    } else if (control.type === 'menu') {
      input = element('select');
      control.menu.forEach(item => {
        let label = item.label;
        if (control.name === 'auto_exposure') {
          label = ({ 1: 'Manual', 3: 'Automatic' })[item.value] || label;
        }
        input.add(new Option(label, String(item.value)));
      });
    } else {
      slider = element('input', 'camera-control-slider');
      slider.type = 'range';
      input = element('input', 'camera-control-number');
      input.type = 'number';
      input.addEventListener('keydown', event => {
        if (event.key === 'Enter') { event.preventDefault(); input.blur(); }
      });
      for (const el of [slider, input]) {
        el.min = control.min / units.scale;
        el.max = control.max / units.scale;
        el.step = Math.max(1, control.step) / units.scale;
        el.setAttribute('aria-label', `${control.label}${units.suffix ? ` (${units.suffix})` : ''}`);
      }
      slider.addEventListener('input', () => { input.value = slider.value; });
      slider.addEventListener('change', () => commit(slider));
      inputs.append(slider);
    }
    input.id = label.htmlFor;
    input.addEventListener('change', () => commit(input));
    inputs.append(input);
    if (units.suffix) inputs.append(element('span', 'camera-control-unit', units.suffix));
    const hint = element('small', 'camera-control-hint');
    hint.id = `${label.htmlFor}-hint`;
    input.setAttribute('aria-describedby', hint.id);
    if (slider) slider.setAttribute('aria-describedby', hint.id);
    input.setAttribute('aria-label', `${control.label}${units.suffix ? ` (${units.suffix})` : ''}`);
    row.append(header, inputs, hint);
    this.rows.set(control.name, { row, header, label, input, slider, hint, units, isToggle, toggleValues });

    const commit = source => {
      if (source.disabled || this.model.busy) return;
      if (!source.checkValidity()) { source.reportValidity(); return; }
      const value = isToggle ? (input.checked ? toggleValues.on : toggleValues.off)
        : Math.round(Number(source.value) * units.scale);
      this.model.perform('', { method: 'PATCH', body: JSON.stringify({ values: { [control.name]: value } }) });
    };
  }

  arrangeControls() {
    const attachedModes = new Set();
    for (const [manual, automatic] of Object.entries(AUTO_CONTROLS)) {
      const manualRow = this.rows.get(manual), automaticRow = this.rows.get(automatic);
      if (!manualRow || !automaticRow) continue;
      automaticRow.row.className = 'camera-control-auto';
      automaticRow.label.textContent = automaticRow.isToggle ? 'Auto' : 'Mode';
      manualRow.header.append(automaticRow.row);
      manualRow.pairedAuto = true;
      attachedModes.add(automatic);
    }
    for (const [title, names] of CONTROL_SECTIONS) {
      const visible = names.filter(name => this.rows.has(name) && !attachedModes.has(name));
      if (!visible.length) continue;
      const section = element('details', 'camera-controls-section');
      const summary = element('summary');
      for (const state of ['expand', 'collapse']) {
        const icon = element('img', `camera-section-${state}`);
        icon.src = `${BASE}/dashboard/assets/icons/${state}.svg`;
        icon.alt = '';
        summary.append(icon);
      }
      const heading = element('h3', '', title);
      const grid = element('div', 'camera-controls-grid');
      summary.append(heading);
      section.append(summary, grid);
      for (const name of visible) {
        const { row } = this.rows.get(name);
        if (FULL_WIDTH.has(name)) row.classList.add('camera-control-full');
        if (title === 'Lighting & frame rate') row.classList.add('camera-control-line');
        grid.append(row);
      }
      this.sections.append(section);
    }
  }

  render() {
    const { data, busy, message, error } = this.model;
    const unlocked = !!operatorKey && !!data?.write_enabled;
    const controls = data?.controls || [];
    const signature = JSON.stringify(controls.map(c => [c.name, c.type, c.min, c.max, c.step, c.menu]));
    if (signature !== this.signature) {
      this.signature = signature;
      this.rows.clear();
      this.sections.replaceChildren();
      controls.forEach(c => this.addControl(c));
      this.arrangeControls();
    }
    this.root.setAttribute('aria-busy', String(busy));
    this.refreshButton.disabled = busy;
    this.resetButton.disabled = !unlocked || busy || !controls.length;
    this.saveButton.disabled = this.resetButton.disabled;
    this.loadSelect.disabled = this.resetButton.disabled || !this.model.configs.length;
    const configSignature = JSON.stringify(this.model.configs);
    if (configSignature !== this.configSignature) {
      this.configSignature = configSignature;
      const placeholder = new Option('load config', '');
      placeholder.disabled = true;
      this.loadSelect.replaceChildren(placeholder);
      this.model.configs.forEach(config => this.loadSelect.add(new Option(config.name, config.id)));
      this.loadSelect.value = '';
    }
    this.loadSelect.title = this.model.configs.length ? 'Load a saved configuration' : 'No saved configurations';
    this.undoButton.disabled = this.resetButton.disabled || !this.model.undoToken;
    this.undoButton.title = this.model.undoToken ? 'Undo last change' : 'No change available to undo';
    this.status.textContent = message || (data && !data.write_enabled ? 'Operator access is unavailable. Settings are view only.' : '');
    this.status.classList.toggle('b', error);
    for (const control of controls) {
      const { input, slider, hint, units, isToggle, toggleValues, pairedAuto } = this.rows.get(control.name);
      const unavailable = control.flags.some(f => ['inactive', 'read-only', 'disabled', 'grabbed'].includes(f));
      input.disabled = !unlocked || busy || unavailable;
      if (slider) slider.disabled = input.disabled;
      if (!busy) {
        if (isToggle) input.checked = control.value === toggleValues.on;
        else input.value = control.value / units.scale;
        if (slider) slider.value = input.value;
      }
      const dependency = control.requires;
      const mode = dependency && controls.find(c => c.name === dependency.name);
      hint.textContent = dependency && mode?.value !== dependency.value
        ? (pairedAuto ? '' : 'Switch to manual mode to adjust.')
        : unavailable ? 'Currently unavailable.' : '';
    }
  }
}

export function refreshCameraControls() {
  const visible = new Set([...document.querySelectorAll('.panel.active .camera-controls')]
    .map(el => el.dataset.cameraId));
  visible.forEach(id => models.get(id)?.perform());
}
