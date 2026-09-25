"""FastAPI application – camera monitoring service.

Start locally:
    uvicorn api.main:app --reload --host 127.0.0.1 --port 8100

Environment variables:
    CAMERA_SERVICE_CONFIG   path to YAML config (default: config/development.yaml)
"""

from __future__ import annotations

import asyncio
import json as _json
import logging
import time as _time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query, Response
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from api.cameras import CameraSource, UStreamerCameraSource, build_camera_registry
from api.captures import CaptureResult, CaptureStore
from api.settings import load_settings
from api import stream_metrics

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

# ── Application state ─────────────────────────────────────────────────────────

settings = load_settings()
DASHBOARD_DIR = Path(__file__).resolve().parent.parent / "dashboard"
_cameras: dict[str, CameraSource] = {}
_store: CaptureStore | None = None
_start_time: float = 0.0


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _cameras, _store, _start_time
    _start_time = _time.monotonic()
    _cameras = build_camera_registry(settings)
    _store = CaptureStore(settings.storage.captures_dir)
    # Start stream-latency collectors for µStreamer-backed cameras
    ustreamer_urls = {
        cam_id: src._base_url
        for cam_id, src in _cameras.items()
        if isinstance(src, UStreamerCameraSource)
    }
    if ustreamer_urls:
        stream_metrics.start_collectors(ustreamer_urls)
    log.info("Camera service ready.  Cameras: %s", list(_cameras))
    yield
    stream_metrics.stop_collectors()
    for src in _cameras.values():
        await src.close()


app = FastAPI(
    title="Camera Service",
    description="BPM Lab camera gateway – whiteboard & robot StreamCams",
    version="0.1.0",
    lifespan=lifespan,
)
app.mount(
    "/dashboard/assets",
    StaticFiles(directory=DASHBOARD_DIR / "assets"),
    name="dashboard-assets",
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
    cam_ids = list(_cameras)
    results = await asyncio.gather(*(_cameras[c].is_available() for c in cam_ids))
    statuses = dict(zip(cam_ids, results))
    all_ready = all(statuses.values())
    return JSONResponse(
        status_code=200 if all_ready else 503,
        content={"ready": all_ready, "cameras": statuses},
    )


# ── Camera endpoints ──────────────────────────────────────────────────────────

@app.get("/api/v1/cameras", tags=["cameras"])
async def list_cameras() -> dict[str, Any]:
    """List all configured cameras and their availability."""
    cam_ids = list(_cameras)
    available = await asyncio.gather(*(_cameras[c].is_available() for c in cam_ids))
    return {
        cam_id: {
            "id": cam_id,
            "available": avail,
            "snapshot_url": f"/api/v1/cameras/{cam_id}/snapshot.jpg",
            "stream_url": f"/api/v1/cameras/{cam_id}/stream.mjpeg",
        }
        for cam_id, avail in zip(cam_ids, available)
    }


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
    event_id: str | None = None  # correlation key (e.g. CPEE process/activity id).
    # Omit it for one-off/manual captures — CaptureStore auto-generates a
    # timestamped id in that case; the real per-image filename is always
    # returned in `filenames` regardless of what event_id ends up being.
    cameras: list[str] | None = None
    store: bool = True


class CaptureResponse(BaseModel):
    event_id: str
    captured_at: str
    images: dict[str, str]
    filenames: dict[str, str] = {}   # camera_id → on-disk filename (<camera_id>_<UTC-ts>.jpg)
    errors: dict[str, str] = {}


@app.get("/api/v1/captures", tags=["captures"])
async def list_captures(
    limit: int = Query(default=10, ge=1, le=50),
) -> list[dict[str, Any]]:
    """List stored captures with metadata (event_id, captured_at, image sizes).
    Sorted by creation time, most recent first."""
    captures_dir = settings.storage.captures_dir
    if not captures_dir.exists():
        return []

    dirs = sorted(
        (p for p in captures_dir.iterdir() if p.is_dir()),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )[:limit]

    results: list[dict[str, Any]] = []
    for event_dir in dirs:
        item: dict[str, Any] = {
            "event_id": event_dir.name,
            "captured_at": None,
            "images": {},           # cam_id → file size in bytes
            "filenames": {},        # cam_id → on-disk filename
        }
        meta_path = event_dir / "metadata.json"
        if meta_path.exists():
            try:
                meta = _json.loads(meta_path.read_text())
                item["captured_at"] = meta.get("captured_at")
                filenames = meta.get("filenames", {})
                for cam_id in meta.get("images", {}):
                    # filenames holds the timestamped name; older captures
                    # (written before that convention) fall back to {cam_id}.jpg
                    filename = filenames.get(cam_id) or f"{cam_id}.jpg"
                    img_path = event_dir / filename
                    if img_path.exists():
                        item["images"][cam_id] = img_path.stat().st_size
                        item["filenames"][cam_id] = filename
            except Exception:
                pass
        results.append(item)

    return results


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
        filenames=result.filenames,
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
        filenames=result.filenames,
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

@app.get("/api/v1/stream-metrics", tags=["monitoring"])
async def get_stream_metrics() -> dict[str, Any]:
    """µStreamer per-frame capture-to-send latency (5-second slots, 30-minute history).
    Reads in-memory data only — no camera requests triggered."""
    return stream_metrics.get_metrics()


@app.get("/api/v1/status", tags=["monitoring"])
async def get_status() -> dict[str, Any]:
    """Camera availability and config. Latency is measured client-side."""
    cam_ids = list(_cameras)
    available = await asyncio.gather(*(_cameras[c].is_available() for c in cam_ids))
    camera_statuses = {
        cam_id: {
            "available": avail,
            "resolution": f"{cfg.width}x{cfg.height}" if (cfg := settings.cameras.get(cam_id)) else None,
            "fps": cfg.fps if cfg else None,
        }
        for cam_id, avail in zip(cam_ids, available)
    }
    return {
        "uptime_seconds": round(_time.monotonic() - _start_time),
        "cameras": camera_statuses,
    }


@app.get("/dashboard", response_class=FileResponse, tags=["monitoring"])
async def dashboard() -> FileResponse:
    """Live monitoring dashboard."""
    return FileResponse(DASHBOARD_DIR / "index.html")
