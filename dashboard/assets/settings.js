import { BASE, CAMERAS, CAM_LABEL, retryLivePreview } from './common.js';
import { CameraControlsPanel, CameraControlsAccess, refreshCameraControls } from './controls.js';

const previews = [];
const grid = document.getElementById('settings-grid');

CAMERAS.forEach(id => {
  const column = document.createElement('section');
  column.className = 'camera-settings-column';
  column.setAttribute('aria-labelledby', `settings-title-${id}`);
  const label = document.createElement('div');
  label.id = `settings-title-${id}`;
  label.className = 'cam-lbl';
  label.textContent = CAM_LABEL[id];
  const header = document.createElement('div');
  header.className = 'cam-lbl-row';
  header.append(label);
  const box = document.createElement('div');
  box.className = 'img-box';
  const preview = document.createElement('img');
  preview.id = `settings-img-${id}`;
  preview.alt = `${id} live preview`;
  preview.dataset.src = `${BASE}/api/v1/cameras/${encodeURIComponent(id)}/stream.mjpeg`;
  retryLivePreview(preview);
  previews.push(preview);
  box.append(preview);
  const controls = document.createElement('div');
  controls.className = 'camera-settings-card';
  column.append(header, box, controls);
  grid.append(column);
  new CameraControlsPanel(controls, id, header);
});

new CameraControlsAccess(document.getElementById('settings-access'));

export function setSettingsActive(active) {
  previews.forEach(preview => {
    if (active) {
      if (!preview.getAttribute('src')) preview.src = preview.dataset.src;
    } else {
      preview.removeAttribute('src');
    }
  });
  if (active) refreshCameraControls();
}
