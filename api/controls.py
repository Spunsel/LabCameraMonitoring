"""Discover and update camera V4L2 controls without taking over the stream."""

from __future__ import annotations

import asyncio
import hmac
import logging
import os
import re
from typing import Annotated, Any
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator

from api.settings import Settings
from api.camera_configs import CameraConfigStore

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


class ConfigName(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=80)

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        value = value.strip()
        if not value or any(ord(c) < 32 or ord(c) == 127 for c in value):
            raise ValueError("Enter a name without control characters")
        return value


class UndoRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    undo_token: str = Field(min_length=32, max_length=32, pattern=r"^[a-f0-9]+$")


class CameraControls:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.key = os.environ.get("CAMERA_SERVICE_CONTROLS_TOKEN", "").strip()
        self.locks = {camera_id: asyncio.Lock() for camera_id in settings.cameras}
        self.revisions = {camera_id: uuid4().hex for camera_id in settings.cameras}
        self.undo_records: dict[str, dict[str, Any]] = {}
        self.configs = CameraConfigStore(settings.storage.camera_configs_dir
                                        or settings.storage.captures_dir.parent / "camera-configs")

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
                "controls": list(controls.values()), "revision": self.revisions[camera_id]}

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
        self.device(camera_id)
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
            return await self.apply(camera_id, initial, values)

    @staticmethod
    def snapshot(state: dict) -> dict[str, int]:
        """Save configuration, not fluctuating auto-controlled measurements."""
        controls = {c["name"]: c for c in state["controls"]}
        return {name: c["value"] for name, c in controls.items()
                if not set(c["flags"]) & {"read-only", "disabled", "grabbed", "inactive"}
                and (name not in DEPENDENCIES or
                     controls.get(DEPENDENCIES[name][0], {}).get("value") == DEPENDENCIES[name][1])}

    async def apply(self, camera_id: str, initial: dict, values: dict[str, int],
                    *, undo: bool = False) -> dict:
        """Called with the camera lock held. All mutations share one undo slot."""
        if not values:
            raise HTTPException(409, "No writable camera controls")
        if any(name not in CONTROL_INFO or type(value) is not int for name, value in values.items()):
            raise HTTPException(422, "Invalid saved control values")
        controls = {c["name"]: c for c in initial["controls"]}
        self.validate(values, controls)
        if not undo and all(controls[name]["value"] == value for name, value in values.items()):
            initial["message"] = "Camera settings already match"
            return initial
        previous = self.snapshot(initial)
        # Invalidate earlier undo tokens before the first hardware write.
        self.revisions[camera_id] = uuid4().hex
        record = self.undo_records.get(camera_id) if undo else None
        if record is None:
            record = {"token": uuid4().hex, "values": previous, "expected": None}
        self.undo_records[camera_id] = record
        modes = {mode for mode, _ in DEPENDENCIES.values()}
        ordered = sorted(values, key=lambda name: name not in modes)
        applied = []
        try:
            for name in ordered:
                await self.run(self.device(camera_id), f"--set-ctrl={name}={values[name]}")
                applied.append(name)
            state = await self.read(camera_id)
        except HTTPException as exc:
            try:
                state = await self.read(camera_id)
                record["expected"] = self.snapshot(state)
                state["undo_token"] = record["token"]
            except HTTPException:
                state = None
                self.undo_records.pop(camera_id, None)
            raise HTTPException(exc.status_code, {
                "message": "Some settings may have changed. " + str(exc.detail),
                "applied": applied, "state": state,
            }) from exc
        actual = {c["name"]: c["value"] for c in state["controls"]}
        adjusted = [name for name, value in values.items() if actual.get(name) != value]
        record["expected"] = self.snapshot(state)
        if undo and not adjusted:
            self.undo_records.pop(camera_id, None)
        else:
            state["undo_token"] = record["token"]
        state["message"] = ("Camera adjusted: " + ", ".join(adjusted)
                            if adjusted else "Last change undone" if undo else "Camera settings updated")
        return state

    async def undo(self, camera_id: str, token: str) -> dict:
        self.device(camera_id)
        async with self.locks[camera_id]:
            record = self.undo_records.get(camera_id)
            if record is None or not hmac.compare_digest(record["token"], token):
                raise HTTPException(409, "Undo is no longer available; the camera may have changed elsewhere")
            initial = await self.read(camera_id)
            if record["expected"] != self.snapshot(initial):
                self.undo_records.pop(camera_id, None)
                self.revisions[camera_id] = uuid4().hex
                raise HTTPException(409, "Camera settings changed elsewhere; refresh before making another change")
            return await self.apply(camera_id, initial, record["values"], undo=True)

    async def list_configs(self, camera_id: str) -> dict:
        self.device(camera_id)
        async with self.locks[camera_id]:
            return {"configs": await asyncio.to_thread(self.configs.listing, camera_id)}

    async def save_config(self, camera_id: str, name: str) -> dict:
        device = self.device(camera_id)
        async with self.locks[camera_id]:
            state = await self.read(camera_id)
            values = self.snapshot(state)
            if not values:
                raise HTTPException(409, "No writable camera controls to save")
            config = await asyncio.to_thread(self.configs.save, camera_id, device, name, values)
            state["configs"] = await asyncio.to_thread(self.configs.listing, camera_id)
            state["saved_config_id"] = config["id"]
            state["message"] = "Configuration saved"
            return state

    async def load_config(self, camera_id: str, config_id: str) -> dict:
        device = self.device(camera_id)
        async with self.locks[camera_id]:
            config = await asyncio.to_thread(self.configs.get, camera_id, config_id, device)
            initial = await self.read(camera_id)
            # apply validates the complete saved configuration before any write.
            return await self.apply(camera_id, initial, config["values"])


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


@router.get("/{camera_id}/controls/configs")
async def list_configs(camera_id: str, service: Annotated[CameraControls, Depends(authorized)]):
    """List this camera's saved configurations (operator access required)."""
    return await service.list_configs(camera_id)


@router.post("/{camera_id}/controls/configs")
async def save_config(camera_id: str, config: ConfigName,
                      service: Annotated[CameraControls, Depends(authorized)]):
    """Save the current camera configuration without changing hardware."""
    return await service.save_config(camera_id, config.name)


@router.post("/{camera_id}/controls/configs/{config_id}/load")
async def load_config(camera_id: str, config_id: str,
                      service: Annotated[CameraControls, Depends(authorized)]):
    """Apply a saved configuration for this device and return camera readback."""
    return await service.load_config(camera_id, config_id)


@router.post("/{camera_id}/controls/undo")
async def undo_controls(camera_id: str, change: UndoRequest,
                        service: Annotated[CameraControls, Depends(authorized)]):
    """Undo the last change using the private token returned by that write."""
    return await service.undo(camera_id, change.undo_token)
