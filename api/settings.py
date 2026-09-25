"""camera_service – settings loader.

Values are read (in priority order) from:
  1. Environment variables prefixed CAMERA_SERVICE_
  2. The YAML file pointed to by CAMERA_SERVICE_CONFIG (default: config/development.yaml)
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import AnyHttpUrl, BaseModel, Field
from pydantic_settings import BaseSettings


# ── Per-camera config ─────────────────────────────────────────────────────────

class CameraConfig(BaseModel):
    source: str = "mock"          # "mock" | "v4l2"
    # mock / test
    path: str | None = None       # path to a static JPEG for MockCameraSource
    # v4l2 / µStreamer
    device: str | None = None     # /dev/v4l/by-id/…
    ustreamer_port: int | None = None  # overrides global default
    width: int = 1280
    height: int = 720
    fps: int = 30


# ── µStreamer defaults ────────────────────────────────────────────────────────

class UStreamerConfig(BaseModel):
    whiteboard_port: int = 8101
    robot_port: int = 8102
    host: str = "127.0.0.1"


# ── API config ────────────────────────────────────────────────────────────────

class ApiConfig(BaseModel):
    host: str = "127.0.0.1"
    port: int = 8100
    # Public URL prefix used for saved image links; if unset, use the request URL.
    public_base_url: AnyHttpUrl | None = None


# ── Storage config ────────────────────────────────────────────────────────────

class StorageConfig(BaseModel):
    captures_dir: Path = Path("var/captures")


# ── Root settings ─────────────────────────────────────────────────────────────

class Settings(BaseModel):
    cameras: dict[str, CameraConfig] = Field(
        default_factory=lambda: {
            "whiteboard": CameraConfig(source="mock"),
            "robot": CameraConfig(source="mock"),
        }
    )
    ustreamer: UStreamerConfig = Field(default_factory=UStreamerConfig)
    api: ApiConfig = Field(default_factory=ApiConfig)
    storage: StorageConfig = Field(default_factory=StorageConfig)


def _load_yaml(path: str | Path) -> dict[str, Any]:
    p = Path(path)
    if not p.exists():
        return {}
    with p.open() as f:
        return yaml.safe_load(f) or {}


def load_settings() -> Settings:
    config_file = os.environ.get(
        "CAMERA_SERVICE_CONFIG", "config/development.yaml"
    )
    raw = _load_yaml(config_file)
    return Settings.model_validate(raw)


# Singleton used throughout the application
settings: Settings = load_settings()
