#!/usr/bin/env bash
# Enable camera controls for the existing lab installation. Run with sudo.
set -euo pipefail
if [[ $EUID -ne 0 ]]; then
  printf 'Run: sudo bash deployment/setup-controls.sh\n' >&2
  exit 1
fi
if ! command -v v4l2-ctl >/dev/null; then
  printf 'Install v4l-utils first (Debian/Ubuntu: sudo apt install v4l-utils).\n' >&2
  exit 1
fi
command -v python3 >/dev/null
systemctl cat camera-api.service >/dev/null
getent group video >/dev/null
install -d -m 755 /etc/camera-service /etc/systemd/system/camera-api.service.d
if [[ ! -f /etc/camera-service/controls.env ]]; then
  (umask 077; python3 - <<'PY' > /etc/camera-service/controls.env
import secrets
print('CAMERA_SERVICE_CONTROLS_TOKEN=' + secrets.token_urlsafe(32))
PY
  )
fi
python3 - <<'PY'
from pathlib import Path
keys = [line.split('=', 1)[1].strip() for line in
        Path('/etc/camera-service/controls.env').read_text().splitlines()
        if line.startswith('CAMERA_SERVICE_CONTROLS_TOKEN=')]
if len(keys) != 1 or not keys[0]:
    raise SystemExit('Set one nonempty CAMERA_SERVICE_CONTROLS_TOKEN in /etc/camera-service/controls.env')
PY
chmod 600 /etc/camera-service/controls.env
cat > /etc/systemd/system/camera-api.service.d/controls.conf <<'UNIT'
[Service]
SupplementaryGroups=video
EnvironmentFile=/etc/camera-service/controls.env
UNIT
systemctl daemon-reload
systemctl restart camera-api.service
printf '\nCamera controls enabled. Enter this operator key in the dashboard:\n'
python3 - <<'PY'
from pathlib import Path
for line in Path('/etc/camera-service/controls.env').read_text().splitlines():
    if line.startswith('CAMERA_SERVICE_CONTROLS_TOKEN='):
        print(line.split('=', 1)[1].strip().strip('\"\''))
PY
