"""Discover MJPEG modes and apply them through the fixed-purpose root helper."""
from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
import re
from typing import Annotated
from uuid import uuid4

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field, StrictInt

from api.controls import CameraControls, DEPENDENCIES, authorized

log = logging.getLogger(__name__)
router = APIRouter(prefix='/api/v1/cameras', tags=['capture mode'])
HELPER = Path('/usr/local/libexec/camera-capture-mode')
POLICY = Path('/etc/camera-service/capture-mode-policy.json')


def parse_modes(output: str) -> list[dict]:
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


class CaptureMode(BaseModel):
    model_config = ConfigDict(extra='forbid')
    width: StrictInt = Field(ge=1, le=8192)
    height: StrictInt = Field(ge=1, le=8192)
    fps: StrictInt = Field(ge=1, le=120)


class CaptureModeChange(BaseModel):
    model_config = ConfigDict(extra='forbid')
    mode: CaptureMode
    expected: CaptureMode


class CaptureModes:
    def __init__(self, controls: CameraControls):
        self.controls = controls
        self.settings = controls.settings
        self.tasks: set[asyncio.Task] = set()

    def port(self, camera_id: str) -> int:
        cfg = self.settings.cameras[camera_id]
        return cfg.ustreamer_port or (self.settings.ustreamer.whiteboard_port
                if camera_id == 'whiteboard' else self.settings.ustreamer.robot_port)

    def installed(self, camera_id: str) -> bool:
        try:
            entry = json.loads(POLICY.read_text())[camera_id]
            return HELPER.is_file() and entry == {
                'device': self.controls.device(camera_id), 'port': self.port(camera_id)}
        except (OSError, ValueError, KeyError, TypeError):
            return False

    async def current(self, camera_id: str) -> dict | None:
        try:
            async with httpx.AsyncClient(timeout=2, trust_env=False) as client:
                response = await client.get(f'http://127.0.0.1:{self.port(camera_id)}/state')
                response.raise_for_status()
                source = response.json()['result']['source']
            if not source['online']:
                return None
            mode = CaptureMode(width=source['resolution']['width'], height=source['resolution']['height'],
                               fps=source['desired_fps'])
            return mode.model_dump()
        except (httpx.HTTPError, ValueError, TypeError, KeyError):
            return None

    async def describe(self, camera_id: str) -> dict:
        device = self.controls.device(camera_id)
        modes = parse_modes(await self.controls.run(device, '--list-formats-ext'))
        current = await self.current(camera_id)
        installed = self.installed(camera_id)
        return {'camera_id': camera_id, 'current': current, 'modes': modes,
                'write_enabled': bool(self.controls.key) and installed and bool(current) and bool(modes),
                'message': 'Capture-mode changes are not enabled on the server.' if not installed else
                           'Camera is offline. Refresh when its stream is available.' if current is None else
                           'No supported capture modes reported.' if not modes else ''}

    async def get(self, camera_id: str) -> dict:
        self.controls.device(camera_id)
        async with self.controls.locks[camera_id]:
            return await self.describe(camera_id)

    async def run_helper(self, camera_id: str, desired: dict, expected: dict) -> dict:
        args = [str(mode[k]) for mode in (desired, expected) for k in ('width', 'height', 'fps')]
        try:
            process = await asyncio.create_subprocess_exec(
                '/usr/bin/sudo', '-n', str(HELPER), camera_id, *args,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
            try:
                stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=65)
            except asyncio.TimeoutError:
                process.kill()
                await process.communicate()
                raise HTTPException(504, 'Capture-mode operation timed out. Refresh and check the capture service.')
            result = json.loads(stdout)
            if not isinstance(result, dict) or type(result.get('ok')) is not bool:
                raise ValueError('Invalid helper response')
            if not result['ok'] or process.returncode:
                log.warning('Capture-mode helper failed: %s', stderr.decode(errors='replace'))
                raise HTTPException(result.get('status', 503), result.get('message', 'Capture-mode change failed'))
            return result
        except (OSError, ValueError) as exc:
            raise HTTPException(503, 'Capture-mode helper is unavailable. Run deployment/setup-capture-mode.sh.') from exc

    async def restore_controls(self, camera_id: str, values: dict) -> dict:
        state = await self.controls.read(camera_id)
        controls = {c['name']: c for c in state['controls']}
        changed = {name: value for name, value in values.items() if controls.get(name, {}).get('value') != value}
        # Include saved mode switches when a dependent manual value must be restored.
        for name in list(changed):
            if name in DEPENDENCIES:
                mode, _ = DEPENDENCIES[name]
                if mode in values:
                    changed[mode] = values[mode]
        if changed:
            self.controls.validate(changed, controls)
            modes = {mode for mode, _ in DEPENDENCIES.values()}
            for name in sorted(changed, key=lambda name: name not in modes):
                await self.controls.run(self.controls.device(camera_id), f'--set-ctrl={name}={changed[name]}')
            state = await self.controls.read(camera_id)
            actual = {c['name']: c['value'] for c in state['controls']}
            if any(actual.get(name) != value for name, value in changed.items()):
                raise HTTPException(409, 'Camera adjusted image settings after restart; review the displayed values.')
        return state

    async def update(self, camera_id: str, change: CaptureModeChange) -> dict:
        self.controls.device(camera_id)
        # Keep the transaction and its lock alive if a browser disconnects midway.
        task = asyncio.create_task(self._update(camera_id, change))
        self.tasks.add(task)
        def done(completed):
            self.tasks.discard(completed)
            if not completed.cancelled():
                completed.exception()  # Retrieve errors even when the HTTP caller disconnected.
        task.add_done_callback(done)
        return await asyncio.shield(task)

    async def _update(self, camera_id: str, change: CaptureModeChange) -> dict:
        async with self.controls.locks[camera_id]:
            info = await self.describe(camera_id)
            if not info['write_enabled']:
                raise HTTPException(503, info['message'] or 'Operator access is not configured')
            desired, expected = change.mode.model_dump(), change.expected.model_dump()
            if info['current'] != expected:
                raise HTTPException(409, 'Capture mode changed elsewhere. Refresh and try again.')
            if not any(m['width'] == desired['width'] and m['height'] == desired['height']
                       and desired['fps'] in m['fps'] for m in info['modes']):
                raise HTTPException(422, 'Unsupported MJPEG resolution/frame-rate combination')
            initial = await self.controls.read(camera_id)
            if desired == expected:
                return {**initial, 'capture_mode': info, 'message': 'Capture mode already matches'}
            saved = self.controls.snapshot(initial)
            self.controls.undo_records.pop(camera_id, None)
            self.controls.revisions[camera_id] = uuid4().hex
            failure = None
            try:
                await self.run_helper(camera_id, desired, expected)
            except HTTPException as exc:
                failure = exc
            try:
                state = await self.restore_controls(camera_id, saved)
            except HTTPException as exc:
                failure = HTTPException(503, (str(failure.detail) + ' ' if failure else '') +
                    'Image settings could not be fully restored after the capture-mode operation. ' + str(exc.detail))
                try:
                    state = await self.controls.read(camera_id)
                except HTTPException:
                    state = None
            try:
                info = await self.describe(camera_id)
            except HTTPException:
                info = None
            if not failure and (info is None or info['current'] != desired):
                failure = HTTPException(503, 'Capture mode could not be verified. Refresh and check the capture service.')
            if failure:
                raise HTTPException(failure.status_code, {'message': str(failure.detail),
                    'state': state, 'capture_mode': info})
            return {**state, 'capture_mode': info, 'message': 'Capture mode applied'}

    async def close(self):
        if self.tasks:
            await asyncio.gather(*self.tasks, return_exceptions=True)


def service(request: Request, response: Response) -> CaptureModes:
    response.headers['Cache-Control'] = 'no-store'
    return request.app.state.capture_modes


@router.get('/{camera_id}/controls/capture-mode')
async def get_capture_mode(camera_id: str, manager: Annotated[CaptureModes, Depends(service)]):
    return await manager.get(camera_id)


@router.patch('/{camera_id}/controls/capture-mode')
async def set_capture_mode(camera_id: str, change: CaptureModeChange,
                           manager: Annotated[CaptureModes, Depends(service)],
                           access: Annotated[CameraControls, Depends(authorized)]):
    """Apply a discovered MJPEG mode. Restarts only this camera; checks the previous mode."""
    return await manager.update(camera_id, change)
