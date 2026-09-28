"""Atomic, per-camera storage for operator-created configurations."""

import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException


class CameraConfigStore:
    def __init__(self, root: Path):
        self.root = root

    def path(self, camera_id: str) -> Path:
        # Neither display names nor camera identifiers become filesystem paths.
        return self.root / (hashlib.sha256(camera_id.encode()).hexdigest() + ".json")

    def read(self, camera_id: str) -> list[dict]:
        try:
            document = json.loads(self.path(camera_id).read_text())
            if document["version"] != 1 or document["camera_id"] != camera_id:
                raise ValueError("Invalid configuration file")
            configs = document["configs"]
            if not isinstance(configs, list) or any(
                not isinstance(c, dict) or not isinstance(c.get("id"), str)
                or not isinstance(c.get("name"), str) or not isinstance(c.get("values"), dict)
                or any(name not in c for name in ("device", "created_at"))
                for c in configs
            ):
                raise ValueError("Invalid configurations")
            return configs
        except FileNotFoundError:
            return []
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise HTTPException(503, "Could not read saved camera configurations; check server storage") from exc

    def save(self, camera_id: str, device: str, name: str, values: dict[str, int]) -> dict:
        configs = self.read(camera_id)
        if any(c["name"].casefold() == name.casefold() for c in configs):
            raise HTTPException(409, "A configuration with this name already exists for this camera")
        config = {"id": uuid4().hex, "name": name, "device": device,
                  "created_at": datetime.now(timezone.utc).isoformat(), "values": values}
        configs.append(config)
        temporary = None
        try:
            self.root.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=self.root,
                                             prefix=".config-", delete=False) as file:
                temporary = Path(file.name)
                json.dump({"version": 1, "camera_id": camera_id, "configs": configs}, file)
                file.flush()
                os.fsync(file.fileno())
            os.replace(temporary, self.path(camera_id))
        except OSError as exc:
            raise HTTPException(503, "Could not save configuration; check server storage permissions and space") from exc
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
        return config

    def get(self, camera_id: str, config_id: str, device: str) -> dict:
        config = next((c for c in self.read(camera_id) if c["id"] == config_id), None)
        if config is None:
            raise HTTPException(404, "Saved configuration not found for this camera")
        if config["device"] != device:
            raise HTTPException(409, "This configuration belongs to a different camera device")
        return config

    def listing(self, camera_id: str) -> list[dict]:
        return [{k: c[k] for k in ("id", "name", "created_at")}
                for c in sorted(self.read(camera_id), key=lambda c: c["name"].casefold())]
