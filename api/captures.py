"""Event capture logic.

A *capture* is a synchronized snapshot of one or more cameras saved to disk
and associated with a caller-supplied event_id.  The directory layout is:

    {captures_dir}/{event_id}/whiteboard.jpg
    {captures_dir}/{event_id}/robot.jpg
    {captures_dir}/{event_id}/metadata.json

The CaptureStore is responsible for:
  - Saving image bytes to the right path
  - Writing a metadata.json side-car
  - Reading existing metadata back (for GET /api/v1/captures/{event_id})
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from api.cameras import CameraSource

log = logging.getLogger(__name__)


# ── Models (plain dataclasses to avoid a second Pydantic import here) ─────────

from dataclasses import dataclass, field


@dataclass
class CaptureResult:
    event_id: str
    captured_at: str  # ISO-8601
    images: dict[str, str]  # camera_id → relative URL
    errors: dict[str, str] = field(default_factory=dict)


# ── Store ─────────────────────────────────────────────────────────────────────

class CaptureStore:
    def __init__(self, captures_dir: Path) -> None:
        self._root = captures_dir
        self._root.mkdir(parents=True, exist_ok=True)

    # ── write ──

    async def capture(
        self,
        event_id: str,
        cameras: dict[str, "CameraSource"],
        camera_ids: list[str] | None = None,
        store: bool = True,
    ) -> CaptureResult:
        """Snapshot the requested cameras, optionally persist the images."""
        now = datetime.now(tz=timezone.utc).isoformat(timespec="milliseconds")
        ids_to_capture = camera_ids or list(cameras.keys())

        # Fetch all cameras concurrently
        tasks = {
            cam_id: asyncio.create_task(cameras[cam_id].snapshot())
            for cam_id in ids_to_capture
            if cam_id in cameras
        }
        results: dict[str, bytes] = {}
        errors: dict[str, str] = {}

        for cam_id, task in tasks.items():
            try:
                results[cam_id] = await task
            except Exception as exc:
                log.warning("Capture %s / camera %s failed: %s", event_id, cam_id, exc)
                errors[cam_id] = str(exc)

        image_urls: dict[str, str] = {}

        if store and results:
            event_dir = self._root / event_id
            event_dir.mkdir(parents=True, exist_ok=True)

            for cam_id, data in results.items():
                img_path = event_dir / f"{cam_id}.jpg"
                img_path.write_bytes(data)
                image_urls[cam_id] = f"/api/v1/captures/{event_id}/{cam_id}.jpg"

            # Write metadata side-car
            meta = {
                "event_id": event_id,
                "captured_at": now,
                "images": image_urls,
                "errors": errors,
            }
            (event_dir / "metadata.json").write_text(json.dumps(meta, indent=2))

        return CaptureResult(
            event_id=event_id,
            captured_at=now,
            images=image_urls,
            errors=errors,
        )

    # ── read ──

    def get(self, event_id: str) -> CaptureResult | None:
        """Return stored metadata for event_id, or None if not found."""
        meta_path = self._root / event_id / "metadata.json"
        if not meta_path.exists():
            return None
        raw = json.loads(meta_path.read_text())
        return CaptureResult(**raw)

    def image_path(self, event_id: str, camera_id: str) -> Path | None:
        p = self._root / event_id / f"{camera_id}.jpg"
        return p if p.exists() else None
