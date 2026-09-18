"""Unit tests for the camera abstraction layer."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from api.cameras import MockCameraSource
from api.settings import CameraConfig


# ── MockCameraSource ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_mock_returns_bytes_from_fixture():
    cfg = CameraConfig(source="mock", path="tests/fixtures/whiteboard.jpg")
    src = MockCameraSource("whiteboard", cfg)
    data = await src.snapshot()
    assert isinstance(data, bytes)
    assert len(data) > 100
    # JPEG magic bytes
    assert data[:2] == b"\xff\xd8"


@pytest.mark.asyncio
async def test_mock_always_available():
    cfg = CameraConfig(source="mock")
    src = MockCameraSource("robot", cfg)
    assert await src.is_available() is True


@pytest.mark.asyncio
async def test_mock_synthetic_fallback_when_no_path():
    """Returns a synthetic JPEG when no fixture path is given."""
    cfg = CameraConfig(source="mock", path=None)
    src = MockCameraSource("whiteboard", cfg)
    data = await src.snapshot()
    assert data[:2] == b"\xff\xd8"


@pytest.mark.asyncio
async def test_mock_close_is_idempotent():
    cfg = CameraConfig(source="mock")
    src = MockCameraSource("robot", cfg)
    await src.close()
    await src.close()  # must not raise


# ── build_camera_registry ─────────────────────────────────────────────────────

def test_registry_contains_configured_cameras():
    from api.cameras import build_camera_registry
    from api.settings import Settings, CameraConfig

    settings = Settings(
        cameras={
            "cam-a": CameraConfig(source="mock"),
            "cam-b": CameraConfig(source="mock"),
        }
    )
    registry = build_camera_registry(settings)
    assert set(registry.keys()) == {"cam-a", "cam-b"}


def test_registry_raises_on_unknown_source():
    from api.cameras import build_camera_registry
    from api.settings import Settings, CameraConfig

    settings = Settings(
        cameras={"bad": CameraConfig(source="unknown_source")}
    )
    with pytest.raises(ValueError, match="Unknown camera source"):
        build_camera_registry(settings)
