"""Event capture logic.

A *capture* is one camera snapshot saved to disk under a server-generated
event_id. The directory layout is:

    {captures_dir}/{event_id}/{camera_id}_20260924T143027482Z.jpg
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

import json
import logging
import secrets
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from api.cameras import CameraSource

log = logging.getLogger(__name__)
CAPTURE_RETENTION = timedelta(days=2)


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


def _generate_event_id(at: datetime) -> str:
    """Generate a timestamped, collision-resistant folder ID for one image."""
    ts = at.strftime("%Y%m%dT%H%M%S") + f"{at.microsecond // 1000:03d}Z"
    return f"capture-{ts}-{secrets.token_hex(8)}"


# ── Store ─────────────────────────────────────────────────────────────────────

class CaptureStore:
    def __init__(self, captures_dir: Path) -> None:
        self._root = captures_dir
        self._root.mkdir(parents=True, exist_ok=True)

    def prune_expired(self, now: datetime | None = None) -> tuple[int, int]:
        """Remove stored capture events older than 48 hours.

        Use the capture timestamp in metadata, falling back to the directory
        modification time for older or damaged entries. Also remove orphaned
        JPEGs from legacy event directories whose IDs were reused before
        duplicate event IDs were rejected.

        Returns (removed_event_directories, removed_orphan_images).
        """
        current = now or datetime.now(tz=timezone.utc)
        if current.tzinfo is None:
            raise ValueError("prune_expired requires a timezone-aware datetime")
        cutoff = current - CAPTURE_RETENTION
        cutoff_timestamp = cutoff.timestamp()
        removed_events = 0
        removed_images = 0

        for event_dir in self._root.iterdir():
            # Never follow a symlink out of the capture storage directory.
            if event_dir.is_symlink() or not event_dir.is_dir():
                continue
            try:
                meta_path = event_dir / "metadata.json"
                try:
                    raw = json.loads(meta_path.read_text())
                    captured_at = datetime.fromisoformat(
                        raw["captured_at"].replace("Z", "+00:00")
                    )
                    if captured_at.tzinfo is None:
                        captured_at = captured_at.replace(tzinfo=timezone.utc)
                    captured_timestamp = captured_at.timestamp()
                except (OSError, ValueError, KeyError, TypeError, AttributeError):
                    captured_timestamp = event_dir.stat().st_mtime

                if captured_timestamp < cutoff_timestamp:
                    shutil.rmtree(event_dir)
                    removed_events += 1
                    continue

                for image in event_dir.iterdir():
                    if (image.is_symlink() or not image.is_file()
                            or image.suffix.lower() != ".jpg"):
                        continue
                    if image.stat().st_mtime < cutoff_timestamp:
                        image.unlink()
                        removed_images += 1
            except OSError as exc:
                log.warning("Could not prune capture %s: %s", event_dir, exc)

        return removed_events, removed_images

    # ── write ──

    async def capture(
        self,
        camera_id: str,
        camera: "CameraSource",
    ) -> CaptureResult:
        """Snapshot one camera and persist its image.

        Each event ID belongs to one saved capture. The server generates a
        unique ID and stores the image and metadata under that directory.
        """
        now_dt = datetime.now(tz=timezone.utc)
        now = now_dt.isoformat(timespec="milliseconds")
        event_id = _generate_event_id(now_dt)
        try:
            data = await camera.snapshot()
        except Exception as exc:
            log.warning("Capture %s / camera %s failed: %s", event_id, camera_id, exc)
            return CaptureResult(event_id=event_id, captured_at=now, images={}, errors={camera_id: str(exc)})

        # mkdir is atomic: even if generated IDs collide, an existing image
        # can never be overwritten. Try a fresh ID if that happens.
        for _ in range(5):
            event_dir = self._root / event_id
            try:
                event_dir.mkdir(parents=True, exist_ok=False)
                break
            except FileExistsError:
                event_id = _generate_event_id(now_dt)
        else:
            raise RuntimeError("Could not allocate a unique capture ID")
        try:
            filename = _timestamp_filename(camera_id, now_dt)
            img_path = event_dir / filename
            img_path.write_bytes(data)
            # The public URL pattern stays {camera_id}.jpg regardless of the
            # on-disk filename — get_capture_image() resolves the real file.
            image_urls = {camera_id: f"/api/v1/captures/{event_id}/{camera_id}.jpg"}
            filenames = {camera_id: filename}

            meta = {
                "event_id": event_id,
                "captured_at": now,
                "images": image_urls,
                "filenames": filenames,
                "errors": {},
            }
            (event_dir / "metadata.json").write_text(json.dumps(meta, indent=2))
        except OSError:
            shutil.rmtree(event_dir, ignore_errors=True)
            raise

        return CaptureResult(
            event_id=event_id,
            captured_at=now,
            images=image_urls,
            filenames=filenames,
            errors={},
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
