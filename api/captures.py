"""Event capture logic.

A *capture* is a synchronized snapshot of one or more cameras saved to disk
and associated with a caller-supplied event_id.  The directory layout is:

    {captures_dir}/{event_id}/whiteboard_20260924T143027482Z.jpg
    {captures_dir}/{event_id}/robot_20260924T143027482Z.jpg
    {captures_dir}/{event_id}/metadata.json

Image filenames always follow ``<camera_id>_YYYYMMDDTHHMMSSmmmZ.jpg`` (UTC,
millisecond precision) — applied here unconditionally, for every caller
(dashboard "capture snapshot" button, CPEE, or any other API client). This
is the single place that decides the on-disk filename, so the convention
cannot drift between call sites.

The CaptureStore is responsible for:
  - Saving image bytes under the timestamped filename
  - Writing a metadata.json side-car (which records the exact filename used
    per camera, so lookups don't need to reconstruct it)
  - Reading existing metadata back (for GET /api/v1/captures/{event_id})

Captures written before this naming convention was introduced used a plain
``{camera_id}.jpg`` filename with no metadata "filenames" key — both
`image_path()` and the list endpoint fall back to that legacy name.
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
    filenames: dict[str, str] = field(default_factory=dict)  # camera_id → on-disk filename
    errors: dict[str, str] = field(default_factory=dict)


def _timestamp_filename(camera_id: str, at: datetime) -> str:
    """<camera_id>_YYYYMMDDTHHMMSSmmmZ.jpg — UTC, millisecond precision."""
    ts = at.strftime("%Y%m%dT%H%M%S") + f"{at.microsecond // 1000:03d}Z"
    return f"{camera_id}_{ts}.jpg"


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
        now_dt = datetime.now(tz=timezone.utc)
        now = now_dt.isoformat(timespec="milliseconds")
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
        filenames: dict[str, str] = {}

        if store and results:
            event_dir = self._root / event_id
            event_dir.mkdir(parents=True, exist_ok=True)

            for cam_id, data in results.items():
                filename = _timestamp_filename(cam_id, now_dt)
                img_path = event_dir / filename
                img_path.write_bytes(data)
                filenames[cam_id] = filename
                # The public URL pattern stays {camera_id}.jpg regardless of the
                # on-disk filename — get_capture_image() resolves the real file.
                image_urls[cam_id] = f"/api/v1/captures/{event_id}/{cam_id}.jpg"

            # Write metadata side-car
            meta = {
                "event_id": event_id,
                "captured_at": now,
                "images": image_urls,
                "filenames": filenames,
                "errors": errors,
            }
            (event_dir / "metadata.json").write_text(json.dumps(meta, indent=2))

        return CaptureResult(
            event_id=event_id,
            captured_at=now,
            images=image_urls,
            filenames=filenames,
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
        """Resolve the on-disk file for camera_id within event_id.

        Reads the real filename from metadata.json (the timestamped name).
        Falls back to the legacy ``{camera_id}.jpg`` for captures written
        before the timestamped-filename convention existed.
        """
        event_dir = self._root / event_id
        filename: str | None = None
        meta_path = event_dir / "metadata.json"
        if meta_path.exists():
            try:
                meta = json.loads(meta_path.read_text())
                filename = meta.get("filenames", {}).get(camera_id)
            except Exception:
                filename = None
        if not filename:
            filename = f"{camera_id}.jpg"  # legacy naming fallback
        p = event_dir / filename
        return p if p.exists() else None
