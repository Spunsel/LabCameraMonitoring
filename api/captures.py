"""Saved camera snapshots and JSON sidecars.

New captures are flat pairs in ``captures_dir``::

    whiteboard_20260926T071520889Z.jpg
    whiteboard_20260926T071520889Z.json

The shared filename stem identifies one snapshot. Older event directories are
still readable until the normal 48-hour cleanup removes them.
"""

from __future__ import annotations

import json
import logging
import re
import secrets
import shutil
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from api.cameras import CameraSource

log = logging.getLogger(__name__)
CAPTURE_RETENTION = timedelta(days=2)
_STEM = re.compile(r"^(?P<camera>[A-Za-z0-9_-]+)_(?P<time>[0-9]{8}T[0-9]{9}Z)$")
_LEGACY_ID = re.compile(r"^[A-Za-z0-9_-]+$")


@dataclass
class CaptureResult:
    camera_id: str
    captured_at: str
    filename: str
    image_url: str


def _timestamp(at: datetime) -> str:
    return at.strftime("%Y%m%dT%H%M%S") + f"{at.microsecond // 1000:03d}Z"


def _jpeg_dimensions(data: bytes) -> tuple[int, int]:
    """Read actual width and height from a JPEG frame header."""
    if not data.startswith(b"\xff\xd8"):
        raise ValueError("Not a JPEG image")
    pos = 2
    while pos < len(data):
        if data[pos] != 0xFF:
            break
        while pos < len(data) and data[pos] == 0xFF:
            pos += 1
        if pos >= len(data):
            break
        marker = data[pos]
        pos += 1
        if marker == 0xD8 or marker == 0x01 or 0xD0 <= marker <= 0xD7:
            continue
        if marker in (0xD9, 0xDA):
            break
        if pos + 2 > len(data):
            break
        segment_size = int.from_bytes(data[pos:pos + 2], "big")
        if segment_size < 2 or pos + segment_size > len(data):
            break
        if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7,
                      0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
            if segment_size >= 7:
                height = int.from_bytes(data[pos + 3:pos + 5], "big")
                width = int.from_bytes(data[pos + 5:pos + 7], "big")
                if width and height:
                    return width, height
            break
        pos += segment_size
    raise ValueError("JPEG frame dimensions not found")


def _stem_time(stem: str) -> datetime | None:
    match = _STEM.fullmatch(stem)
    if not match:
        return None
    try:
        return datetime.strptime(match.group("time"), "%Y%m%dT%H%M%S%fZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _sort_time(value: Any, fallback: float) -> float:
    try:
        at = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if at.tzinfo is None:
            at = at.replace(tzinfo=timezone.utc)
        return at.timestamp()
    except (AttributeError, TypeError, ValueError, OverflowError):
        return fallback


class CaptureStore:
    def __init__(self, captures_dir: Path) -> None:
        self._root = captures_dir
        self._root.mkdir(parents=True, exist_ok=True)

    async def capture(self, camera_id: str, camera: CameraSource) -> CaptureResult:
        """Save one camera JPEG; publish the JSON only after the image exists."""
        if not re.fullmatch(r"[A-Za-z0-9_-]+", camera_id):
            raise ValueError("Invalid camera ID for a capture filename")
        try:
            data = await camera.snapshot()
            width_px, height_px = _jpeg_dimensions(data)
        except Exception as exc:
            log.warning("Camera %s failed to capture: %s", camera_id, exc)
            raise RuntimeError(f"Camera {camera_id!r} failed to capture") from exc

        received_at = datetime.now(tz=timezone.utc)
        # Exclusive creation works across workers/processes, not just tasks.
        for offset in range(10_000):
            stem = f"{camera_id}_{_timestamp(received_at + timedelta(milliseconds=offset))}"
            image_path = self._root / f"{stem}.jpg"
            meta_path = self._root / f"{stem}.json"
            if meta_path.exists():
                continue
            try:
                with image_path.open("xb") as image:
                    try:
                        image.write(data)
                    except BaseException:
                        image_path.unlink(missing_ok=True)
                        raise
            except FileExistsError:
                continue

            temp_path = self._root / f".{stem}.{secrets.token_hex(4)}.json.tmp"
            metadata = {
                "camera_id": camera_id,
                "captured_at": received_at.isoformat(timespec="milliseconds"),
                "filename": image_path.name,
                "size_bytes": len(data),
                "width_px": width_px,
                "height_px": height_px,
                "content_type": "image/jpeg",
            }
            try:
                # A JSON file is the completion marker for the pair. A reader
                # never sees partially written metadata or a half-written JPEG.
                with temp_path.open("x", encoding="utf-8") as temp:
                    json.dump(metadata, temp, indent=2)
                    temp.write("\n")
                temp_path.replace(meta_path)
            except BaseException:
                temp_path.unlink(missing_ok=True)
                image_path.unlink(missing_ok=True)
                raise

            return CaptureResult(
                camera_id=camera_id,
                captured_at=metadata["captured_at"],
                filename=image_path.name,
                image_url=f"/api/v1/captures/{image_path.name}",
            )
        raise OSError("Could not allocate a unique snapshot filename")

    def flat_metadata(self, stem: str) -> dict[str, Any] | None:
        """Return a complete, valid flat pair; ignore unfinished writes."""
        match = _STEM.fullmatch(stem)
        if match is None or _stem_time(stem) is None:
            return None
        meta_path = self._root / f"{stem}.json"
        image_path = self._root / f"{stem}.jpg"
        if (meta_path.is_symlink() or image_path.is_symlink()
                or not meta_path.is_file() or not image_path.is_file()):
            return None
        try:
            raw = json.loads(meta_path.read_text(encoding="utf-8"))
            if (not isinstance(raw, dict) or raw.get("camera_id") != match.group("camera")
                    or raw.get("filename") != image_path.name
                    or not isinstance(raw.get("captured_at"), str)):
                return None
            return raw
        except (OSError, ValueError, TypeError):
            return None

    def flat_image_path(self, stem: str) -> Path | None:
        if self.flat_metadata(stem) is None:
            return None
        return self._root / f"{stem}.jpg"

    def get_legacy(self, event_id: str) -> dict[str, Any] | None:
        """Read metadata for a capture saved in the previous folder layout."""
        if not _LEGACY_ID.fullmatch(event_id):
            return None
        meta_path = self._root / event_id / "metadata.json"
        if meta_path.is_symlink() or not meta_path.is_file():
            return None
        try:
            raw = json.loads(meta_path.read_text(encoding="utf-8"))
            return raw if isinstance(raw, dict) and raw.get("event_id") == event_id else None
        except (OSError, ValueError):
            return None

    def legacy_image_path(self, event_id: str, camera_id: str) -> Path | None:
        raw = self.get_legacy(event_id)
        if raw is None or not _LEGACY_ID.fullmatch(camera_id):
            return None
        filenames = raw.get("filenames")
        if not isinstance(filenames, dict):
            filenames = {}
        filename = filenames.get(camera_id) or f"{camera_id}.jpg"
        if not isinstance(filename, str) or Path(filename).name != filename or not filename.endswith(".jpg"):
            return None
        path = self._root / event_id / filename
        return path if not path.is_symlink() and path.is_file() else None

    def list_captures(self, limit: int) -> list[dict[str, Any]]:
        """List new pairs and older event folders, newest first."""
        candidates: list[tuple[float, Path]] = []
        for path in self._root.iterdir():
            if path.is_symlink():
                continue
            try:
                if path.is_file() and path.suffix == ".json":
                    saved_at = _stem_time(path.stem)
                    if saved_at is not None:
                        candidates.append((saved_at.timestamp(), path))
                elif path.is_dir():
                    candidates.append((path.stat().st_mtime, path))
            except OSError as exc:
                log.warning("Could not inspect capture %s: %s", path, exc)

        candidates.sort(key=lambda item: item[0], reverse=True)
        results: list[dict[str, Any]] = []
        for _, path in candidates:
            if len(results) == limit:
                break
            try:
                if path.is_file():
                    raw = self.flat_metadata(path.stem)
                    if raw is None:
                        continue
                    image_path = self._root / raw["filename"]
                    cam_id = raw["camera_id"]
                    results.append({
                        "camera_id": cam_id,
                        "captured_at": raw["captured_at"],
                        "images": {cam_id: image_path.stat().st_size},
                        "filenames": {cam_id: image_path.name},
                    })
                elif path.is_dir():
                    raw = self.get_legacy(path.name)
                    if raw is None:
                        continue
                    sizes: dict[str, int] = {}
                    filenames: dict[str, str] = {}
                    for cam_id in raw.get("images", {}):
                        image_path = self.legacy_image_path(path.name, cam_id)
                        if image_path is not None:
                            sizes[cam_id] = image_path.stat().st_size
                            filenames[cam_id] = image_path.name
                    results.append({
                        "event_id": path.name,
                        "captured_at": raw.get("captured_at"),
                        "images": sizes,
                        "filenames": filenames,
                    })
            except (OSError, ValueError, TypeError, AttributeError) as exc:
                log.warning("Could not list capture %s: %s", path, exc)
        return results

    def prune_expired(self, now: datetime | None = None) -> tuple[int, int]:
        """Delete flat pairs and legacy folders older than 48 hours."""
        current = now or datetime.now(tz=timezone.utc)
        if current.tzinfo is None:
            raise ValueError("prune_expired requires a timezone-aware datetime")
        cutoff = current - CAPTURE_RETENTION
        removed_captures = 0
        removed_orphans = 0

        for path in self._root.iterdir():
            if path.is_symlink():
                continue
            try:
                if path.is_file() and path.suffix == ".json":
                    saved_at = _stem_time(path.stem)
                    if saved_at is None or saved_at >= cutoff:
                        continue
                    image_path = self._root / f"{path.stem}.jpg"
                    if image_path.is_file() and not image_path.is_symlink():
                        image_path.unlink()
                    path.unlink()
                    removed_captures += 1
                elif path.is_file() and path.suffix == ".jpg":
                    saved_at = _stem_time(path.stem)
                    # Orphans left by interrupted writes have no JSON marker.
                    if (saved_at is not None and saved_at < cutoff
                            and not (self._root / f"{path.stem}.json").exists()
                            and path.exists()):
                        path.unlink()
                        removed_orphans += 1
                elif path.is_dir():
                    raw = self.get_legacy(path.name)
                    captured = _sort_time(raw.get("captured_at") if raw else None, path.stat().st_mtime)
                    if captured < cutoff.timestamp():
                        shutil.rmtree(path)
                        removed_captures += 1
                    else:
                        for image in path.iterdir():
                            if (image.is_file() and not image.is_symlink()
                                    and image.suffix.lower() == ".jpg"
                                    and image.stat().st_mtime < cutoff.timestamp()):
                                image.unlink()
                                removed_orphans += 1
            except OSError as exc:
                log.warning("Could not prune capture %s: %s", path, exc)
        return removed_captures, removed_orphans
