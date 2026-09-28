#!/usr/bin/python3 -I
"""Root-installed, fixed-purpose capture-mode transaction. No application imports."""
import fcntl
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
from urllib.request import build_opener, ProxyHandler

POLICY = Path('/etc/camera-service/capture-mode-policy.json')
MODE_DIR = Path('/etc/camera-service/capture-modes')
LOCK_DIR = Path('/run/camera-service-mode')
CAMERAS = {'whiteboard', 'robot'}
ENV = {'PATH': '/usr/bin:/usr/sbin', 'LC_ALL': 'C'}


def parse_modes(output):
    """Only discrete MJPEG modes and whole FPS accepted by uStreamer --desired-fps."""
    found = {}
    mjpeg = False
    size = None
    for line in output.splitlines():
        fmt = re.search(r"\[\d+\]:\s+'([^']+)'", line)
        if fmt:
            mjpeg = fmt[1] == 'MJPG'
            size = None
        match = re.search(r'Size: Discrete (\d+)x(\d+)', line)
        if 'Size:' in line:
            size = (int(match[1]), int(match[2])) if mjpeg and match else None
        interval = re.search(r'Interval: Discrete .*\(([\d.]+) fps\)', line)
        if size and interval:
            rate = float(interval[1])
            if rate.is_integer() and 1 <= rate <= 120:
                found.setdefault(size, set()).add(int(rate))
    return [{'width': w, 'height': h, 'fps': sorted(rates, reverse=True)}
            for (w, h), rates in sorted(found.items(), key=lambda item: item[0][0]*item[0][1], reverse=True)]


def command(args, timeout=8):
    return subprocess.run(args, capture_output=True, text=True, env=ENV,
                          timeout=timeout, check=True).stdout


def state(port):
    opener = build_opener(ProxyHandler({}))
    with opener.open(f'http://127.0.0.1:{port}/state', timeout=1) as response:
        source = json.load(response)['result']['source']
    try:
        if not source['online']:
            raise ValueError('Camera is offline')
        return {'width': int(source['resolution']['width']),
                'height': int(source['resolution']['height']), 'fps': int(source['desired_fps'])}
    except (KeyError, TypeError) as error:
        raise ValueError('Invalid camera state') from error


def wait_mode(port, mode):
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        try:
            if state(port) == mode:
                return True
        except (OSError, ValueError, KeyError):
            pass
        time.sleep(0.25)
    return False


def atomic_write(path, data):
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix='.mode-', delete=False) as output:
            temporary = Path(output.name)
            output.write(data)
            output.flush()
            os.fsync(output.fileno())
            os.fchmod(output.fileno(), 0o644)
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def transact(camera, desired, expected, entry):
    if state(entry['port']) != expected:
        return {'ok': False, 'status': 409, 'message': 'Capture mode changed elsewhere. Refresh and try again.'}
    available = parse_modes(command(['/usr/bin/v4l2-ctl', '--device', entry['device'], '--list-formats-ext']))
    if not any(m['width'] == desired['width'] and m['height'] == desired['height']
               and desired['fps'] in m['fps'] for m in available):
        return {'ok': False, 'status': 422, 'message': 'Unsupported MJPEG resolution/frame-rate combination'}
    if desired == expected:
        return {'ok': True, 'current': expected}
    path = MODE_DIR / f'{camera}.env'
    if path.is_symlink():
        raise ValueError('Invalid mode file')
    old = path.read_bytes() if path.exists() else None
    data = f"RESOLUTION={desired['width']}x{desired['height']}\nFPS={desired['fps']}\n".encode()
    unit = f'camera-capture@{camera}.service'
    atomic_write(path, data)
    try:
        command(['/usr/bin/systemctl', 'restart', unit])
        if not wait_mode(entry['port'], desired):
            raise ValueError('The new mode did not come online')
        return {'ok': True, 'current': desired}
    except (OSError, ValueError, subprocess.SubprocessError):
        # The original override (or absence of one) is restored before restarting.
        try:
            if old is None:
                path.unlink(missing_ok=True)
            else:
                atomic_write(path, old)
            command(['/usr/bin/systemctl', 'restart', unit])
            recovered = wait_mode(entry['port'], expected)
        except (OSError, ValueError, subprocess.SubprocessError):
            recovered = False
        return {'ok': False, 'status': 503, 'rolled_back': recovered,
                'message': 'New capture mode failed; previous mode restored.' if recovered else
                'New capture mode failed and recovery could not be confirmed. Check the capture service.'}


def main(argv):
    if os.geteuid() != 0:
        raise ValueError('This helper must run through its installed sudo rule')
    if len(argv) != 7 or argv[0] not in CAMERAS or any(not re.fullmatch(r'[0-9]{1,5}', x) for x in argv[1:]):
        raise ValueError('Invalid capture-mode arguments')
    camera = argv[0]
    desired = dict(zip(('width', 'height', 'fps'), map(int, argv[1:4])))
    expected = dict(zip(('width', 'height', 'fps'), map(int, argv[4:7])))
    for mode in (desired, expected):
        if not 1 <= mode['width'] <= 8192 or not 1 <= mode['height'] <= 8192 or not 1 <= mode['fps'] <= 120:
            raise ValueError('Invalid capture mode')
    entry = json.loads(POLICY.read_text())[camera]
    if not isinstance(entry['device'], str) or not entry['device'].startswith('/dev/'):
        raise ValueError('Invalid device policy')
    if type(entry['port']) is not int or not 1024 <= entry['port'] <= 65535:
        raise ValueError('Invalid port policy')
    LOCK_DIR.mkdir(mode=0o755, exist_ok=True)
    with (LOCK_DIR / f'{camera}.lock').open('a') as lock:
        # Concurrent callers must retry, not queue unbounded privileged processes.
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return {'ok': False, 'status': 409, 'message': 'Capture mode is already being changed'}
        return transact(camera, desired, expected, entry)


if __name__ == '__main__':
    try:
        result = main(sys.argv[1:])
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
        print(f'Capture-mode helper: {type(error).__name__}', file=sys.stderr)
        result = {'ok': False, 'status': 503, 'message': 'Capture-mode operation failed; check installation and service logs'}
    print(json.dumps(result))
    sys.exit(0 if result['ok'] else 1)
