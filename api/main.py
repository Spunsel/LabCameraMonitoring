"""FastAPI application – camera monitoring service.

Start locally:
    uvicorn api.main:app --reload --host 127.0.0.1 --port 8100

Environment variables:
    CAMERA_SERVICE_CONFIG   path to YAML config (default: config/development.yaml)
"""

from __future__ import annotations

import asyncio
import logging
import time as _time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI, HTTPException, Response
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel

from api.cameras import CameraSource, build_camera_registry
from api.captures import CaptureResult, CaptureStore
from api.dashboard import DASHBOARD_HTML
from api.settings import load_settings

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

# ── Application state ─────────────────────────────────────────────────────────

settings = load_settings()
_cameras: dict[str, CameraSource] = {}
_store: CaptureStore | None = None
_start_time: float = 0.0


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _cameras, _store, _start_time
    _start_time = _time.monotonic()
    _cameras = build_camera_registry(settings)
    _store = CaptureStore(settings.storage.captures_dir)
    log.info("Camera service ready.  Cameras: %s", list(_cameras))
    yield
    for src in _cameras.values():
        await src.close()


app = FastAPI(
    title="Camera Service",
    description="BPM Lab camera gateway – whiteboard & robot StreamCams",
    version="0.1.0",
    lifespan=lifespan,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat(timespec="milliseconds")


def _get_camera(camera_id: str) -> CameraSource:
    cam = _cameras.get(camera_id)
    if cam is None:
        raise HTTPException(status_code=404, detail=f"Unknown camera {camera_id!r}")
    return cam


# ── Health endpoints (no auth) ────────────────────────────────────────────────

@app.get("/healthz", tags=["health"])
async def healthz() -> dict[str, str]:
    """The API process is running."""
    return {"status": "ok"}


@app.get("/readyz", tags=["health"])
async def readyz() -> dict[str, Any]:
    """All configured cameras are delivering frames."""
    statuses = {
        cam_id: await src.is_available()
        for cam_id, src in _cameras.items()
    }
    all_ready = all(statuses.values())
    return JSONResponse(
        status_code=200 if all_ready else 503,
        content={"ready": all_ready, "cameras": statuses},
    )


# ── Camera endpoints ──────────────────────────────────────────────────────────

@app.get("/api/v1/cameras", tags=["cameras"])
async def list_cameras() -> dict[str, Any]:
    """List all configured cameras and their availability."""
    result = {}
    for cam_id, src in _cameras.items():
        result[cam_id] = {
            "id": cam_id,
            "available": await src.is_available(),
            "snapshot_url": f"/api/v1/cameras/{cam_id}/snapshot.jpg",
            "stream_url": f"/api/v1/cameras/{cam_id}/stream.mjpeg",
        }
    return result


@app.get(
    "/api/v1/cameras/{camera_id}/snapshot.jpg",
    tags=["cameras"],
    response_class=Response,
)
async def get_snapshot(camera_id: str) -> Response:
    """Return the latest JPEG snapshot for a camera."""
    cam = _get_camera(camera_id)
    try:
        data = await cam.snapshot()
    except RuntimeError:
        raise HTTPException(status_code=503, detail=f"Camera {camera_id!r} unavailable")

    return Response(
        content=data,
        media_type="image/jpeg",
        headers={
            "Cache-Control": "no-store",
            "X-Camera-Id": camera_id,
            "X-Captured-At": _now_iso(),
        },
    )


@app.get(
    "/api/v1/cameras/{camera_id}/stream.mjpeg",
    tags=["cameras"],
)
async def get_stream(camera_id: str, fps: int = 10) -> StreamingResponse:
    """MJPEG live stream.  Polls the camera at `fps` frames per second."""
    _get_camera(camera_id)  # validate camera exists

    async def _generate():
        interval = 1.0 / max(1, min(fps, 30))
        while True:
            cam = _cameras.get(camera_id)
            if cam is None:
                break
            try:
                data = await cam.snapshot()
                yield (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n\r\n" + data + b"\r\n"
                )
            except RuntimeError:
                # Camera temporarily unavailable – send a short pause
                pass
            await asyncio.sleep(interval)

    return StreamingResponse(
        _generate(),
        media_type="multipart/x-mixed-replace; boundary=frame",
        headers={"Cache-Control": "no-store", "X-Camera-Id": camera_id},
    )


# ── Capture endpoints ─────────────────────────────────────────────────────────

class CaptureRequest(BaseModel):
    event_id: str
    cameras: list[str] | None = None
    store: bool = True


class CaptureResponse(BaseModel):
    event_id: str
    captured_at: str
    images: dict[str, str]
    errors: dict[str, str] = {}


@app.get("/api/v1/captures", tags=["captures"])
async def list_captures() -> list[str]:
    """List stored capture event IDs, most recent first (max 20)."""
    captures_dir = settings.storage.captures_dir
    if not captures_dir.exists():
        return []
    ids = sorted(
        (p.name for p in captures_dir.iterdir() if p.is_dir()),
        reverse=True,
    )
    return ids[:20]


@app.post(
    "/api/v1/captures",
    tags=["captures"],
    response_model=CaptureResponse,
    status_code=201,
)
async def create_capture(req: CaptureRequest) -> CaptureResponse:
    """Capture one or more cameras and (optionally) persist the images."""
    if _store is None:
        raise HTTPException(status_code=503, detail="Service not ready")
    result: CaptureResult = await _store.capture(
        event_id=req.event_id,
        cameras=_cameras,
        camera_ids=req.cameras,
        store=req.store,
    )
    if not result.images and result.errors:
        raise HTTPException(status_code=503, detail="All cameras failed to capture")
    return CaptureResponse(
        event_id=result.event_id,
        captured_at=result.captured_at,
        images=result.images,
        errors=result.errors,
    )


@app.get(
    "/api/v1/captures/{event_id}",
    tags=["captures"],
    response_model=CaptureResponse,
)
async def get_capture(event_id: str) -> CaptureResponse:
    """Retrieve metadata for a previously stored capture."""
    if _store is None:
        raise HTTPException(status_code=503, detail="Service not ready")
    result = _store.get(event_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Capture {event_id!r} not found")
    return CaptureResponse(
        event_id=result.event_id,
        captured_at=result.captured_at,
        images=result.images,
        errors=result.errors,
    )


@app.get(
    "/api/v1/captures/{event_id}/{camera_id}.jpg",
    tags=["captures"],
    response_class=Response,
)
async def get_capture_image(event_id: str, camera_id: str) -> Response:
    """Return the stored JPEG for a specific camera in a capture event."""
    if _store is None:
        raise HTTPException(status_code=503, detail="Service not ready")
    path = _store.image_path(event_id, camera_id)
    if path is None:
        raise HTTPException(status_code=404, detail="Image not found")
    return Response(
        content=path.read_bytes(),
        media_type="image/jpeg",
        headers={
            "Cache-Control": "no-store",
            "X-Camera-Id": camera_id,
            "X-Event-Id": event_id,
        },
    )


# ── Monitoring endpoints ───────────────────────────────────────────────────────

@app.get("/api/v1/status", tags=["monitoring"])
async def get_status() -> dict[str, Any]:
    """Camera availability and config. Latency is measured client-side."""
    camera_statuses: dict[str, Any] = {}
    for cam_id, src in _cameras.items():
        available = await src.is_available()
        cfg = settings.cameras.get(cam_id)
        camera_statuses[cam_id] = {
            "available": available,
            "resolution": f"{cfg.width}x{cfg.height}" if cfg else None,
            "fps": cfg.fps if cfg else None,
        }

    return {
        "uptime_seconds": round(_time.monotonic() - _start_time),
        "cameras": camera_statuses,
    }


@app.get("/dashboard", response_class=HTMLResponse, tags=["monitoring"])
async def dashboard() -> str:
    """Live monitoring dashboard."""
    return DASHBOARD_HTML
