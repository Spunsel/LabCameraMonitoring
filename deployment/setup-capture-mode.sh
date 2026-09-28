#!/usr/bin/env bash
# Install narrowly scoped capture-mode privileges. Existing camera modes stay unchanged.
set -euo pipefail
if [[ $EUID -ne 0 ]]; then
  printf 'Run: sudo bash deployment/setup-capture-mode.sh\n' >&2
  exit 1
fi
script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
for program in python3 systemctl sudo visudo v4l2-ctl; do
  command -v "$program" >/dev/null || { printf 'Required command missing: %s\n' "$program" >&2; exit 1; }
done
[[ -x /usr/bin/python3 && -x /usr/bin/systemctl && -x /usr/bin/v4l2-ctl && -x /usr/bin/sudo ]]
api_user=$(systemctl show camera-api.service --property=User --value)
[[ "$api_user" =~ ^[a-z_][a-z0-9_-]*$ && "$api_user" != root ]] || { printf 'Expected a non-root API service user.\n' >&2; exit 1; }
# Stage and validate everything before installation. Read actual running device/port.
stage_dir=$(mktemp -d)
trap 'rm -rf -- "$stage_dir"' EXIT
python3 - "$stage_dir/policy.json" <<'PY'
import json
from pathlib import Path
import subprocess
import sys

policy = {}
for camera in ('whiteboard', 'robot'):
    unit = f'camera-capture@{camera}.service'
    start = subprocess.check_output(['systemctl', 'show', unit, '-p', 'ExecStart', '--value'], text=True)
    if '--resolution=${RESOLUTION}' not in start or '--desired-fps=${FPS}' not in start:
        raise SystemExit(f'{unit}: ExecStart must use --resolution=${{RESOLUTION}} and --desired-fps=${{FPS}}')
    pid = int(subprocess.check_output(['systemctl', 'show', unit, '-p', 'MainPID', '--value'], text=True))
    if pid <= 0:
        raise SystemExit(f'Start {unit} before running setup')
    args = Path(f'/proc/{pid}/cmdline').read_bytes().decode().rstrip('\0').split('\0')
    def option(name):
        for index, arg in enumerate(args):
            if arg.startswith(name + '='):
                return arg.split('=', 1)[1]
            if arg == name:
                return args[index + 1]
        raise SystemExit(f'{unit}: missing {name}')
    device, port = option('--device'), int(option('--port'))
    if not device.startswith('/dev/') or not 1024 <= port <= 65535:
        raise SystemExit(f'{unit}: invalid device or port')
    policy[camera] = {'device': device, 'port': port}
Path(sys.argv[1]).write_text(json.dumps(policy, indent=2) + '\n')
PY
printf '%s ALL=(root) NOPASSWD: /usr/local/libexec/camera-capture-mode *\n' "$api_user" > "$stage_dir/sudoers"
visudo -cf "$stage_dir/sudoers"
install -d -o root -g root -m 755 /usr/local/libexec /etc/camera-service/capture-modes /etc/sudoers.d
install -o root -g root -m 755 "$script_dir/capture-mode-helper.py" /usr/local/libexec/camera-capture-mode
install -o root -g root -m 644 "$stage_dir/policy.json" /etc/camera-service/capture-mode-policy.json
install -o root -g root -m 440 "$stage_dir/sudoers" /etc/sudoers.d/camera-capture-mode
for camera in whiteboard robot; do
  dropin_dir="/etc/systemd/system/camera-capture@$camera.service.d"
  install -d -o root -g root -m 755 "$dropin_dir"
  printf '[Service]\nEnvironmentFile=-/etc/camera-service/capture-modes/%s.env\n' "$camera" > "$dropin_dir/90-capture-mode.conf"
  chmod 644 "$dropin_dir/90-capture-mode.conf"
done
systemctl daemon-reload
systemctl restart camera-api.service
printf '\nCapture-mode controls enabled. Reload the dashboard. Capture services were not restarted.\n'
