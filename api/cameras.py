"""Camera abstraction layer.

Two concrete sources are provided:

  MockCameraSource        – returns a static JPEG from disk; for local dev.
  UStreamerCameraSource   – fetches JPEG snapshots from a running µStreamer
                            process over HTTP; used in production on lab.

All sources implement the CameraSource protocol:

    async def snapshot() -> bytes          – current JPEG frame
    async def is_available() -> bool       – True when the camera is delivering frames
    async def close() -> None              – release resources

The registry `build_camera_registry(settings)` constructs the right source for
each configured camera and returns a dict[str, CameraSource].
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Protocol

import httpx

from api.settings import CameraConfig, Settings

log = logging.getLogger(__name__)


# ── Protocol / interface ──────────────────────────────────────────────────────

class CameraSource(Protocol):
    camera_id: str

    async def snapshot(self) -> bytes:
        """Return a JPEG-encoded frame.  Raises RuntimeError when unavailable."""
        ...

    async def is_available(self) -> bool:
        """True when a recent frame can be obtained."""
        ...

    async def close(self) -> None:
        """Release any held resources."""
        ...


# ── Mock source (local development) ──────────────────────────────────────────

class MockCameraSource:
    """Returns a static JPEG from disk.  Falls back to a small synthetic image
    when no path is configured (requires Pillow)."""

    def __init__(self, camera_id: str, config: CameraConfig) -> None:
        self.camera_id = camera_id
        self._path: Path | None = Path(config.path) if config.path else None
        self._cached: bytes | None = None

    # ── helpers ──

    def _load(self) -> bytes:
        if self._path and self._path.exists():
            return self._path.read_bytes()
        return self._synthetic_jpeg()

    @staticmethod
    def _synthetic_jpeg() -> bytes:
        try:
            from io import BytesIO
            from PIL import Image, ImageDraw  # type: ignore

            img = Image.new("RGB", (640, 480), color=(30, 30, 30))
            draw = ImageDraw.Draw(img)
            draw.text((20, 20), "Mock camera – no fixture found", fill=(200, 200, 200))
            buf = BytesIO()
            img.save(buf, format="JPEG", quality=80)
            return buf.getvalue()
        except ImportError:
            # Minimal valid 1×1 JPEG (generated offline)
            return (
                b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
                b"\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07\t\t"
                b"\x08\n\x0c\x14\r\x0c\x0b\x0b\x0c\x19\x12\x13\x0f\x14\x1d\x1a"
                b"\x1f\x1e\x1d\x1a\x1c\x1c $.' \",#\x1c\x1c(7),01444\x1f'9=82<.342\x1e"
                b"\xff\xc0\x00\x0b\x08\x00\x01\x00\x01\x01\x01\x11\x00"
                b"\xff\xc4\x00\x1f\x00\x00\x01\x05\x01\x01\x01\x01\x01\x01\x00"
                b"\x00\x00\x00\x00\x00\x00\x00\x01\x02\x03\x04\x05\x06\x07\x08"
                b"\t\n\x0b\xff\xc4\x00\xb5\x10\x00\x02\x01\x03\x03\x02\x04\x03"
                b"\x05\x05\x04\x04\x00\x00\x01}\x01\x02\x03\x00\x04\x11\x05\x12"
                b"!1A\x06\x13Qa\x07\"q\x142\x81\x91\xa1\x08#B\xb1\xc1\x15R\xd1"
                b"\xf0$3br\x82\t\n\x16\x17\x18\x19\x1a%&'()*456789:CDEFGHIJ"
                b"STUVWXYZcdefghijstuvwxyz\x83\x84\x85\x86\x87\x88\x89\x8a\x92"
                b"\x93\x94\x95\x96\x97\x98\x99\x9a\xa2\xa3\xa4\xa5\xa6\xa7\xa8"
                b"\xa9\xaa\xb2\xb3\xb4\xb5\xb6\xb7\xb8\xb9\xba\xc2\xc3\xc4\xc5"
                b"\xc6\xc7\xc8\xc9\xca\xd2\xd3\xd4\xd5\xd6\xd7\xd8\xd9\xda\xe1"
                b"\xe2\xe3\xe4\xe5\xe6\xe7\xe8\xe9\xea\xf1\xf2\xf3\xf4\xf5\xf6"
                b"\xf7\xf8\xf9\xfa\xff\xda\x00\x08\x01\x01\x00\x00?\x00\xfb\xd6"
                b"\xff\xd9"
            )

    # ── CameraSource interface ──

    async def snapshot(self) -> bytes:
        if self._cached is None:
            self._cached = self._load()
        return self._cached

    async def is_available(self) -> bool:
        return True

    async def close(self) -> None:
        pass


# ── µStreamer source (production) ─────────────────────────────────────────────

class UStreamerCameraSource:
    """Fetches JPEG snapshots from a µStreamer instance running on localhost.

    µStreamer exposes:
      GET /?action=snapshot  →  image/jpeg
    """

    _SNAPSHOT_PATH = "/?action=snapshot"
    _HEALTH_PATH = "/?action=ping"
    _TIMEOUT = httpx.Timeout(5.0)

    def __init__(self, camera_id: str, config: CameraConfig, port: int) -> None:
        self.camera_id = camera_id
        self._base_url = f"http://127.0.0.1:{port}"
        self._client: httpx.AsyncClient | None = None

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self._base_url,
                timeout=self._TIMEOUT,
                follow_redirects=False,
            )
        return self._client

    async def snapshot(self) -> bytes:
        client = self._get_client()
        try:
            resp = await client.get(self._SNAPSHOT_PATH)
            resp.raise_for_status()
            return resp.content
        except Exception as exc:
            log.warning("Camera %s snapshot failed: %s", self.camera_id, exc)
            raise RuntimeError(f"Camera {self.camera_id!r} unavailable") from exc

    async def is_available(self) -> bool:
        client = self._get_client()
        try:
            resp = await client.get(self._HEALTH_PATH)
            return resp.status_code == 200
        except Exception:
            return False

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()


# ── Registry builder ──────────────────────────────────────────────────────────

def build_camera_registry(settings: Settings) -> dict[str, CameraSource]:
    """Construct one CameraSource per configured camera."""
    registry: dict[str, CameraSource] = {}
    default_ports = {
        "whiteboard": settings.ustreamer.whiteboard_port,
        "robot": settings.ustreamer.robot_port,
    }

    for cam_id, cfg in settings.cameras.items():
        if cfg.source == "mock":
            registry[cam_id] = MockCameraSource(cam_id, cfg)
            log.info("Camera %r → MockCameraSource (path=%s)", cam_id, cfg.path)
        elif cfg.source == "v4l2":
            port = cfg.ustreamer_port or default_ports.get(cam_id, 8101)
            registry[cam_id] = UStreamerCameraSource(cam_id, cfg, port)
            log.info(
                "Camera %r → UStreamerCameraSource (device=%s, port=%d)",
                cam_id, cfg.device, port,
            )
        else:
            raise ValueError(f"Unknown camera source {cfg.source!r} for camera {cam_id!r}")

    return registry
