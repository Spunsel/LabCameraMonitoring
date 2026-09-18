"""Shared pytest fixtures."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

# Point at the development config so tests use MockCameraSource
os.environ.setdefault("CAMERA_SERVICE_CONFIG", "config/development.yaml")


@pytest.fixture(scope="session")
def client(tmp_path_factory):
    """FastAPI TestClient with a per-session temporary captures directory."""
    captures_dir = tmp_path_factory.mktemp("captures")

    # Override storage location before the app loads settings
    from api import settings as _settings_module
    from api.settings import load_settings, Settings, StorageConfig

    new_settings = load_settings()
    new_settings.storage.captures_dir = captures_dir
    _settings_module.settings = new_settings

    from api.main import app
    with TestClient(app) as c:
        yield c
