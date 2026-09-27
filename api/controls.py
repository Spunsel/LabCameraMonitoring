"""Discover and update camera V4L2 controls without taking over the stream."""

from __future__ import annotations

import asyncio
import hmac
import logging
import os
import re
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, ConfigDict, Field, StrictInt

from api.settings import Settings

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/cameras", tags=["camera controls"])
operator_key = APIKeyHeader(name="X-Camera-Control-Key", auto_error=False)

# Only image controls are writable. Device paths and command arguments never
# come from the request. Ranges, steps, flags and menus come from the driver.
CONTROL_INFO = {
    "zoom_absolute": ("Zoom", "basic"),
    "pan_absolute": ("Pan", "basic"),
    "tilt_absolute": ("Tilt", "basic"),
    "focus_automatic_continuous": ("Autofocus", "basic"),
    "focus_absolute": ("Focus", "basic"),
    "auto_exposure": ("Exposure mode", "basic"),
    "exposure_time_absolute": ("Exposure", "basic"),
    "white_balance_automatic": ("Auto white balance", "basic"),
    "white_balance_temperature": ("White balance", "basic"),
    "brightness": ("Brightness", "advanced"),
    "contrast": ("Contrast", "advanced"),
    "saturation": ("Saturation", "advanced"),
    "sharpness": ("Sharpness", "advanced"),
    "gain": ("Gain", "advanced"),
    "power_line_frequency": ("Anti-flicker", "advanced"),
    "backlight_compensation": ("Backlight compensation", "advanced"),
    "exposure_dynamic_framerate": ("Allow variable frame rate", "advanced"),
}
DEPENDENCIES = {
    "focus_absolute": ("focus_automatic_continuous", 0),
    "exposure_time_absolute": ("auto_exposure", 1),
    "white_balance_temperature": ("white_balance_automatic", 0),
}
CONTROL_LINE = re.compile(r"^\s*(\w+)\s+0x[0-9a-fA-F]+\s+\(([^)]+)\)\s*:\s*(.*)$")
MENU_LINE = re.compile(r"^\s+(-?\d+):\s+(.+)$")


def parse_controls(output: str) -> dict[str, dict[str, Any]]:
    """Parse LC_ALL=C v4l2-ctl --list-ctrls-menus output, including sparse menus."""
    controls: dict[str, dict[str, Any]] = {}
    current = None
    for line in output.splitlines():
        match = CONTROL_LINE.match(line)
        if match:
            name, kind, attributes = match.groups()
            current = None
            if name not in CONTROL_INFO or kind not in {"int", "bool", "menu"}:
                continue
            numbers = {k: int(v) for k, v in re.findall(
                r"\b(min|max|step|default|value)=(-?\d+)", attributes
            )}
            if "value" not in numbers:
                continue
            label, group = CONTROL_INFO[name]
            current = {
                "name": name, "label": label, "group": group, "type": kind,
                "min": 0, "max": 1, "step": 1, **numbers, "menu": [],
                "flags": [],
            }
            flags = re.search(r"\bflags=(.*)$", attributes)
            if flags:
                current["flags"] = [f.strip() for f in flags[1].split(",")]
            if name in DEPENDENCIES:
                mode, value = DEPENDENCIES[name]
                current["requires"] = {"name": mode, "value": value}
            controls[name] = current
        elif current is not None and current["type"] == "menu":
            menu = MENU_LINE.match(line)
            if menu:
                current["menu"].append({"value": int(menu[1]), "label": menu[2]})
    return {name: controls[name] for name in CONTROL_INFO if name in controls}


class ControlChanges(BaseModel):
    model_config = ConfigDict(extra="forbid")
    values: dict[str, StrictInt] = Field(min_length=1, max_length=len(CONTROL_INFO))


class CameraControls:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.key = os.environ.get("CAMERA_SERVICE_CONTROLS_TOKEN", "").strip()
        self.locks = {camera_id: asyncio.Lock() for camera_id in settings.cameras}

    def device(self, camera_id: str) -> str:
        cfg = self.settings.cameras.get(camera_id)
        if cfg is None:
            raise HTTPException(404, "Unknown camera")
        if cfg.source != "v4l2":
            raise HTTPException(409, "Camera settings are available only for physical cameras")
        if not cfg.device or not cfg.device.startswith("/dev/"):
            raise HTTPException(503, "Camera device is not configured; check cameras.<id>.device")
        return cfg.device

    def authorize(self, key: str | None) -> None:
        if not self.key:
            raise HTTPException(503, "Operator access is not configured")
        if not key or len(key) > 512 or not hmac.compare_digest(
            key.encode("utf-8"), self.key.encode("utf-8")
        ):
            raise HTTPException(403, "Invalid operator key")

    async def run(self, device: str, argument: str) -> str:
        try:
            process = await asyncio.create_subprocess_exec(
                "v4l2-ctl", "--device", device, argument,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
                env={**os.environ, "LC_ALL": "C"},
            )
        except FileNotFoundError as exc:
            raise HTTPException(503, "Camera controls require v4l-utils on the server") from exc
        except OSError as exc:
            raise HTTPException(503, "Could not start the camera controls utility") from exc
        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=3)
        except (asyncio.TimeoutError, asyncio.CancelledError) as exc:
            if process.returncode is None:
                try:
                    process.kill()
                except ProcessLookupError:
                    pass
            await process.communicate()
            if isinstance(exc, asyncio.CancelledError):
                raise
            raise HTTPException(504, "Camera control request timed out") from exc
        if process.returncode:
            message = (stderr + stdout).decode("utf-8", errors="replace").strip()
            log.warning("V4L2 control failed for %s: %s", device, message)
            if "Permission denied" in message:
                detail = "Camera permission denied; give camera-api.service access to the video group"
            elif "Device or resource busy" in message:
                detail = "Camera rejected this change while busy; refresh and try again"
            else:
                detail = "Camera unavailable or control rejected; refresh settings and check the service log"
            raise HTTPException(503, detail)
        return stdout.decode("utf-8", errors="replace")

    async def read(self, camera_id: str) -> dict[str, Any]:
        controls = parse_controls(await self.run(self.device(camera_id), "--list-ctrls-menus"))
        return {"camera_id": camera_id, "write_enabled": bool(self.key),
                "controls": list(controls.values())}

    async def get(self, camera_id: str) -> dict[str, Any]:
        self.device(camera_id)
        async with self.locks[camera_id]:
            return await self.read(camera_id)

    @staticmethod
    def validate(values: dict[str, int], controls: dict[str, dict[str, Any]]) -> None:
        for name, value in values.items():
            control = controls.get(name)
            if control is None:
                raise HTTPException(422, f"Unsupported control: {name}")
            flags = set(control["flags"])
            if flags & {"read-only", "disabled", "grabbed"}:
                raise HTTPException(409, f"Control is not writable: {name}")
            if not control["min"] <= value <= control["max"]:
                raise HTTPException(422, f"Value outside camera range: {name}")
            if (value - control["min"]) % max(1, control["step"]):
                raise HTTPException(422, f"Value does not match camera step: {name}")
            if control["type"] == "menu" and value not in {m["value"] for m in control["menu"]}:
                raise HTTPException(422, f"Unsupported menu value: {name}")
            dependency = DEPENDENCIES.get(name)
            if dependency:
                mode, manual = dependency
                final_mode = values.get(mode, controls.get(mode, {}).get("value"))
                if final_mode != manual:
                    raise HTTPException(409, f"Select manual mode before changing {name}")
                # An inactive manual control becomes available after its auto mode changes.
                if "inactive" in flags and not (mode in values and controls[mode]["value"] != manual):
                    raise HTTPException(409, f"Control is currently inactive: {name}")
            elif "inactive" in flags:
                raise HTTPException(409, f"Control is currently inactive: {name}")

    async def update(self, camera_id: str, values: dict[str, int] | None) -> dict[str, Any]:
        device = self.device(camera_id)
        async with self.locks[camera_id]:
            initial = await self.read(camera_id)
            controls = {c["name"]: c for c in initial["controls"]}
            if values is None:  # Restore camera defaults; auto modes own their manual values.
                values = {name: c["default"] for name, c in controls.items()
                          if "default" in c and not set(c["flags"]) & {"read-only", "disabled", "grabbed"}
                          and "inactive" not in c["flags"]}
                values = {name: value for name, value in values.items()
                          if name not in DEPENDENCIES or
                          values.get(DEPENDENCIES[name][0], controls.get(DEPENDENCIES[name][0], {}).get("value"))
                          == DEPENDENCIES[name][1]}
            if not values:
                raise HTTPException(409, "No writable camera controls")
            self.validate(values, controls)
            # Turn off automatic modes before writing dependent manual values.
            modes = {mode for mode, _ in DEPENDENCIES.values()}
            ordered = sorted(values, key=lambda name: name not in modes)
            applied = []
            try:
                for name in ordered:
                    await self.run(device, f"--set-ctrl={name}={values[name]}")
                    applied.append(name)
                state = await self.read(camera_id)
            except HTTPException as exc:
                if not applied:
                    raise
                try:
                    state = await self.read(camera_id)
                except HTTPException:
                    state = None
                raise HTTPException(exc.status_code, {
                    "message": "Some settings may have changed. " + str(exc.detail),
                    "applied": applied, "state": state,
                }) from exc
            actual = {c["name"]: c["value"] for c in state["controls"]}
            adjusted = [name for name, value in values.items() if actual.get(name) != value]
            state["message"] = ("Camera adjusted: " + ", ".join(adjusted)
                                if adjusted else "Camera settings updated")
            return state


def manager(request: Request, response: Response) -> CameraControls:
    response.headers["Cache-Control"] = "no-store"
    return request.app.state.camera_controls


async def authorized(service: Annotated[CameraControls, Depends(manager)],
                     key: Annotated[str | None, Depends(operator_key)]) -> CameraControls:
    service.authorize(key)
    return service


@router.get("/{camera_id}/controls")
async def get_controls(camera_id: str, service: Annotated[CameraControls, Depends(manager)]):
    """Current supported controls, device limits, menu options and automatic-mode flags."""
    return await service.get(camera_id)


@router.get("/{camera_id}/controls/access")
async def check_access(camera_id: str, service: Annotated[CameraControls, Depends(authorized)]):
    service.device(camera_id)
    return {"authorized": True}


@router.patch("/{camera_id}/controls")
async def change_controls(camera_id: str, changes: ControlChanges,
                          service: Annotated[CameraControls, Depends(authorized)]):
    """Apply validated integer control values and return the camera's readback."""
    return await service.update(camera_id, changes.values)


@router.post("/{camera_id}/controls/reset")
async def reset_controls(camera_id: str, service: Annotated[CameraControls, Depends(authorized)]):
    """Restore reported device defaults for writable controls, including automatic modes."""
    return await service.update(camera_id, None)
