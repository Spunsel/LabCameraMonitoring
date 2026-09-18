"""Tests for the HTTP API endpoints."""

from __future__ import annotations


# ── Health ────────────────────────────────────────────────────────────────────

def test_healthz(client):
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_readyz_all_cameras_available(client):
    resp = client.get("/readyz")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ready"] is True
    assert set(body["cameras"]) == {"whiteboard", "robot"}


# ── Camera list ───────────────────────────────────────────────────────────────

def test_list_cameras(client):
    resp = client.get("/api/v1/cameras")
    assert resp.status_code == 200
    body = resp.json()
    assert "whiteboard" in body
    assert "robot" in body
    for cam in body.values():
        assert "snapshot_url" in cam
        assert "stream_url" in cam
        assert cam["available"] is True


def test_list_cameras_unknown_does_not_appear(client):
    resp = client.get("/api/v1/cameras")
    assert "nonexistent" not in resp.json()


# ── Snapshots ─────────────────────────────────────────────────────────────────

def test_snapshot_whiteboard(client):
    resp = client.get("/api/v1/cameras/whiteboard/snapshot.jpg")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "image/jpeg"
    assert resp.headers["cache-control"] == "no-store"
    assert resp.headers["x-camera-id"] == "whiteboard"
    assert "x-captured-at" in resp.headers
    assert len(resp.content) > 100


def test_snapshot_robot(client):
    resp = client.get("/api/v1/cameras/robot/snapshot.jpg")
    assert resp.status_code == 200
    assert resp.headers["x-camera-id"] == "robot"


def test_snapshot_unknown_camera_returns_404(client):
    resp = client.get("/api/v1/cameras/nonexistent/snapshot.jpg")
    assert resp.status_code == 404


# ── Event captures ────────────────────────────────────────────────────────────

def test_capture_both_cameras(client):
    resp = client.post(
        "/api/v1/captures",
        json={"event_id": "test-event-001", "cameras": ["whiteboard", "robot"], "store": True},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["event_id"] == "test-event-001"
    assert "whiteboard" in body["images"]
    assert "robot" in body["images"]
    assert "captured_at" in body


def test_capture_single_camera(client):
    resp = client.post(
        "/api/v1/captures",
        json={"event_id": "test-event-002", "cameras": ["whiteboard"], "store": True},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert "whiteboard" in body["images"]
    assert "robot" not in body["images"]


def test_capture_no_store(client):
    resp = client.post(
        "/api/v1/captures",
        json={"event_id": "test-nostored-001", "store": False},
    )
    assert resp.status_code == 201
    # images dict is empty when store=False
    assert resp.json()["images"] == {}


def test_get_capture_metadata(client):
    # create first
    client.post(
        "/api/v1/captures",
        json={"event_id": "meta-test-001", "store": True},
    )
    resp = client.get("/api/v1/captures/meta-test-001")
    assert resp.status_code == 200
    assert resp.json()["event_id"] == "meta-test-001"


def test_get_capture_not_found(client):
    resp = client.get("/api/v1/captures/does-not-exist")
    assert resp.status_code == 404


def test_get_capture_image(client):
    client.post(
        "/api/v1/captures",
        json={"event_id": "img-test-001", "store": True},
    )
    resp = client.get("/api/v1/captures/img-test-001/whiteboard.jpg")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "image/jpeg"


def test_get_capture_image_not_found(client):
    resp = client.get("/api/v1/captures/does-not-exist/whiteboard.jpg")
    assert resp.status_code == 404
