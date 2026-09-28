"""Bounded, process-local request activity. Never consume request/response bodies."""
from collections import deque
from datetime import datetime, timezone
from http import HTTPStatus
import re
from time import perf_counter
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, Query, Request, Response

from api.controls import CameraControls, authorized


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


class ActivityStore:
    def __init__(self, capacity=500):
        self.records = deque(maxlen=capacity)
        self.session_id = uuid4().hex
        self.started_at = utc_now()
        self.sequence = 0

    def append(self, record):
        # No await or I/O: append/sequence form one operation on the API event loop.
        self.sequence += 1
        self.records.append({**record, "id": self.sequence})

    def page(self, after=0, session=None, limit=100):
        oldest = self.records[0]["id"] if self.records else 1
        reset = session != self.session_id or after > self.sequence or after < oldest - 1
        records = [r for r in self.records if reset or r["id"] > after]
        # A single response advances to the latest record; keep the newest limit.
        return {"session_id": self.session_id, "started_at": self.started_at,
                "cursor": self.sequence, "reset": reset,
                "records": list(reversed(records[-limit:]))}


def safe_endpoint(scope):
    """Use known route shapes, allowing only documented, bounded path parameters."""
    route = scope.get("route")
    template = getattr(route, "path", None)
    if not template:
        return "/api/v1/[unmatched]"
    result = template
    for name, value in scope.get("path_params", {}).items():
        value = str(value)
        if name in {"camera_id", "stem", "config_id"} and re.fullmatch(r"[A-Za-z0-9_-]{1,100}", value):
            result = result.replace("{" + name + "}", value)
    return result[:240]


class ActivityMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        path = scope.get("path", "")
        root = scope.get("root_path", "")
        if root and path.startswith(root + "/"):
            path = path[len(root):]
        eligible = path.startswith("/api/v1/") or path in {"/healthz", "/readyz", "/openapi.json"}
        excluded = path.rstrip("/") == "/api/v1/activity" or path.endswith("/stream.mjpeg")
        store = getattr(getattr(scope.get("app"), "state", None), "api_activity", None)
        if scope["type"] != "http" or not eligible or excluded or store is None:
            return await self.app(scope, receive, send)

        background = scope["method"] == "GET" and any(
            k.lower() == b"x-camera-background" and v == b"1" for k, v in scope.get("headers", [])
        )
        started, timestamp, request_id = perf_counter(), utc_now(), uuid4().hex
        status, complete, recorded = 500, False, False

        def record(interrupted=False):
            nonlocal recorded
            if recorded:
                return
            recorded = True
            if background and status < 400 and not interrupted:
                return
            try:
                label = HTTPStatus(status).phrase
            except ValueError:
                label = "Unknown status"
            # Safe summaries only; no arbitrary exception text, credentials or bodies.
            result = {400: "Invalid request", 401: "Authentication required",
                      403: "Access denied", 404: "Not found", 409: "State conflict",
                      422: "Invalid parameters", 500: "Internal server error",
                      503: "Service or camera unavailable", 504: "Request timed out"}.get(status, label)
            filename = scope.get("state", {}).get("activity_capture")
            if status >= 400 or not isinstance(filename, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,100}\.jpg", filename):
                filename = None
            if filename:
                result = filename
            if interrupted:
                result = "Response interrupted" if status < 400 else result
            store.append({"request_id": request_id, "time": timestamp,
                          "method": scope["method"], "endpoint": safe_endpoint(scope),
                          "status": status, "status_text": label,
                          "duration_ms": round((perf_counter() - started) * 1000, 2),
                          "result": result, "capture_filename": filename,
                          "failed": status >= 400 or interrupted})

        async def observed_send(message):
            nonlocal status, complete
            if message["type"] == "http.response.start":
                status = message["status"]
                message = {**message, "headers": [*message.get("headers", []),
                                                   (b"x-request-id", request_id.encode())]}
            await send(message)
            if message["type"] == "http.response.body" and not message.get("more_body", False):
                complete = True
                record()

        try:
            await self.app(scope, receive, observed_send)
        finally:
            record(interrupted=not complete)


router = APIRouter(tags=["monitoring"])


@router.get("/api/v1/activity")
async def get_activity(request: Request, response: Response,
                       access: Annotated[CameraControls, Depends(authorized)],
                       after: int = Query(0, ge=0), session: str | None = Query(None, max_length=32),
                       limit: int = Query(100, ge=1, le=500)):
    """Recent finite API requests. Operator key required; cleared at API restart."""
    response.headers["Cache-Control"] = "no-store"
    return request.app.state.api_activity.page(after, session, limit)
