"""FastAPI application – camera monitoring service.

Start locally:
    uvicorn api.main:app --reload --host 127.0.0.1 --port 8100

Environment variables:
    CAMERA_SERVICE_CONFIG   path to YAML config (default: config/development.yaml)
    CAMERA_SERVICE_CONTROLS_TOKEN   operator key for camera setting changes
"""

from __future__ import annotations

import asyncio
import logging
import time as _time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from api.cameras import CameraSource, UStreamerCameraSource, build_camera_registry
from api.captures import CaptureResult, CaptureStore
from api.controls import CameraControls, router as controls_router
from api.capture_modes import CaptureModes, router as capture_modes_router
from api.settings import load_settings
from api import stream_metrics
from api.activity import ActivityStore, ActivityMiddleware, router as activity_router

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

# ── Application state ─────────────────────────────────────────────────────────

settings = load_settings()
DASHBOARD_DIR = Path(__file__).resolve().parent.parent / "dashboard"
_cameras: dict[str, CameraSource] = {}
_store: CaptureStore | None = None
_start_time: float = 0.0
CAPTURE_CLEANUP_INTERVAL = 60 * 60  # seconds; prune on startup and hourly


async def _capture_cleanup_loop(store: CaptureStore) -> None:
    while True:
        await asyncio.sleep(CAPTURE_CLEANUP_INTERVAL)
        try:
            removed_captures, removed_images = store.prune_expired()
            if removed_captures or removed_images:
                log.info("Pruned %d expired captures and %d old images",
                         removed_captures, removed_images)
        except Exception:
            log.exception("Could not prune expired captures")


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _cameras, _store, _start_time
    _start_time = _time.monotonic()
    app.state.api_activity = ActivityStore()
    _cameras = build_camera_registry(settings)
    app.state.camera_controls = CameraControls(settings)
    app.state.capture_modes = CaptureModes(app.state.camera_controls)
    _store = CaptureStore(settings.storage.captures_dir)
    try:
        removed_captures, removed_images = _store.prune_expired()
        if removed_captures or removed_images:
            log.info("Pruned %d expired captures and %d old images",
                     removed_captures, removed_images)
    except Exception:
        log.exception("Could not prune expired captures at startup")
    # Start stream-latency collectors for µStreamer-backed cameras
    ustreamer_urls = {
        cam_id: src._base_url
        for cam_id, src in _cameras.items()
        if isinstance(src, UStreamerCameraSource)
    }
    if ustreamer_urls:
        stream_metrics.start_collectors(ustreamer_urls)
    log.info("Camera service ready.  Cameras: %s", list(_cameras))
    cleanup_task = asyncio.create_task(_capture_cleanup_loop(_store))
    try:
        yield
    finally:
        await app.state.capture_modes.close()
        cleanup_task.cancel()
        try:
            await cleanup_task
        except asyncio.CancelledError:
            pass
        stream_metrics.stop_collectors()
        for src in _cameras.values():
            await src.close()


app = FastAPI(
    title="Camera Service",
    description="BPM Lab camera gateway – whiteboard & robot StreamCams",
    version="0.1.0",
    lifespan=lifespan,
)
app.add_middleware(ActivityMiddleware)
app.include_router(activity_router)
app.include_router(controls_router)
app.include_router(capture_modes_router)
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
    """Take a fresh snapshot and return JPEG bytes immediately (not stored).

    Use this for the direct-image mode. For a saved image with a retrievable
    link, POST to /api/v1/cameras/{camera_id}/captures instead.
    """
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


def _public_capture_url(request: Request, image_path: str) -> str:
    """Resolve an API image path against the public URL prefix when configured."""
    public_base = settings.api.public_base_url
    base = str(public_base) if public_base is not None else str(request.base_url)
    return urljoin(base.rstrip("/") + "/", image_path.lstrip("/"))


@app.get("/api/v1/captures", tags=["captures"])
async def list_captures(
    limit: int = Query(default=10, ge=1, le=50),
) -> list[dict[str, Any]]:
    """List complete snapshot pairs, newest first."""
    if _store is None:
        raise HTTPException(status_code=503, detail="Service not ready")
    return _store.list_captures(limit)


@app.get("/api/v1/captures/stats", tags=["captures"])
async def capture_storage_stats() -> dict[str, int | str | None]:
    """On-disk JPG/JSON usage and time of the last complete cleanup."""
    if _store is None:
        raise HTTPException(status_code=503, detail="Service not ready")
    return _store.storage_summary()


@app.post(
    "/api/v1/cameras/{camera_id}/captures",
    tags=["captures"],
    response_class=PlainTextResponse,
    status_code=201,
    responses={
        201: {"description": "Image URL in plain text and in the Location header",
              "headers": {"Location": {"schema": {"type": "string", "format": "uri"}}}},
    },
)
async def create_capture(camera_id: str, request: Request) -> PlainTextResponse:
    """Save one snapshot; return its public URL as plain text and Location.

    The POST has no request body. The server saves a JPEG and matching JSON
    for 48 hours. For immediate JPEG bytes without storage,
    use GET /api/v1/cameras/{camera_id}/snapshot.jpg.
    """
    if await request.body():
        raise HTTPException(status_code=400, detail="Capture POST does not accept a request body")
    if _store is None:
        raise HTTPException(status_code=503, detail="Service not ready")
    camera = _get_camera(camera_id)
    try:
        result: CaptureResult = await _store.capture(camera_id=camera_id, camera=camera)
    except RuntimeError:
        raise HTTPException(status_code=503, detail=f"Camera {camera_id!r} failed to capture")
    request.state.activity_capture = result.filename
    image_url = _public_capture_url(request, result.image_url)
    return PlainTextResponse(
        content=image_url + "\n",
        status_code=201,
        headers={"Location": image_url, "Cache-Control": "no-store"},
    )


@app.get("/api/v1/captures/{stem}.jpg", tags=["captures"], response_class=Response)
async def get_saved_image(stem: str) -> Response:
    """Return a JPEG from a complete flat pair."""
    if _store is None:
        raise HTTPException(status_code=503, detail="Service not ready")
    path = _store.flat_image_path(stem)
    if path is None:
        raise HTTPException(status_code=404, detail="Image not found")
    try:
        data = path.read_bytes()
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Image not found")
    return Response(
        content=data,
        media_type="image/jpeg",
        headers={"Cache-Control": "no-store", "X-Camera-Id": stem.rsplit("_", 1)[0]},
    )


@app.get("/api/v1/captures/{stem}.json", tags=["captures"])
async def get_saved_metadata(stem: str) -> JSONResponse:
    """Return the JSON sidecar of a complete flat pair."""
    if _store is None:
        raise HTTPException(status_code=503, detail="Service not ready")
    metadata = _store.flat_metadata(stem)
    if metadata is None:
        raise HTTPException(status_code=404, detail="Capture metadata not found")
    return JSONResponse(content=metadata, headers={"Cache-Control": "no-store"})


# ── Monitoring endpoints ───────────────────────────────────────────────────────

@app.get("/api/v1/stream-metrics", tags=["monitoring"])
async def get_stream_metrics() -> dict[str, Any]:
    """µStreamer per-frame capture-to-send latency (5-second slots, 30-minute history).
    Reads in-memory data only — no camera requests triggered."""
    return stream_metrics.get_metrics()


@app.get("/api/v1/status", tags=["monitoring"])
async def get_status() -> dict[str, Any]:
    """Camera availability and live capture mode. Latency is measured client-side."""
    cam_ids = list(_cameras)
    available = await asyncio.gather(*(_cameras[c].is_available() for c in cam_ids))
    live_modes = await asyncio.gather(*(app.state.capture_modes.current(cam_id)
        if settings.cameras[cam_id].source == "v4l2" else asyncio.sleep(0, result=None)
        for cam_id in cam_ids))
    mode_by_camera = dict(zip(cam_ids, live_modes))
    camera_statuses = {
        cam_id: {
            "available": avail,
            "resolution": (f"{mode['width']}x{mode['height']}" if (mode := mode_by_camera[cam_id])
                           else f"{cfg.width}x{cfg.height}" if (cfg := settings.cameras[cam_id]).source != "v4l2" else None),
            "fps": mode["fps"] if mode else settings.cameras[cam_id].fps
                   if settings.cameras[cam_id].source != "v4l2" else None,
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
