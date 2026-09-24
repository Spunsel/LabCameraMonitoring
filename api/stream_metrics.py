"""Background collector: µStreamer per-frame capture-to-send latency.

Connects to each µStreamer instance with::

    /?action=stream&extra_headers=1&zero_data=1

and reads per-frame ``X-UStreamer-Latency`` values.  ``zero_data=1`` means no
JPEG body is transferred, so the probe costs essentially nothing.

Results are aggregated into 5-second slots (median, max, count) and stored in
a rolling 360-slot (30-minute) deque per camera.  The history lives in memory;
it resets when the API process restarts.
"""

from __future__ import annotations

import asyncio
import logging
import statistics
import time
from collections import deque
from dataclasses import dataclass
from typing import Any

import httpx

log = logging.getLogger(__name__)

INTERVAL_S = 5          # aggregation window in seconds
MAX_SLOTS  = 360        # 30 minutes at 5 s/slot
STALE_SECS = 10         # seconds without a valid frame before state → "stale"
_BACKOFF   = (1, 2, 4, 8, 30)   # reconnect delays in seconds


# ── Data model ────────────────────────────────────────────────────────────────

@dataclass
class Slot:
    timestamp: float    # Unix epoch (UTC)
    median_ms: float
    max_ms:    float
    count:     int

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "median_ms": self.median_ms,
            "max_ms":    self.max_ms,
            "count":     self.count,
        }


# ── Per-camera collector ──────────────────────────────────────────────────────

class CameraCollector:
    """Keeps one persistent header-only MJPEG connection to a µStreamer instance.

    States
    ------
    starting      No valid frame received yet since the last (re)connect.
    live          Fresh frames are arriving.
    stale         No new frame for > STALE_SECS seconds.
    offline       µStreamer is reachable but reports X-UStreamer-Online: false.
    disconnected  The HTTP connection is broken; reconnect is pending.
    """

    def __init__(self, cam_id: str, url: str) -> None:
        self.cam_id = cam_id
        self.url    = url

        self.history: deque[Slot] = deque(maxlen=MAX_SLOTS)
        self.state   = "starting"
        self.latest: Slot | None  = None

        self._task:              asyncio.Task | None = None
        self._pending:           list[float] = []
        self._last_grab:         float = -1.0   # last µStreamer grab timestamp
        self._last_frame_wall:   float = 0.0    # time.monotonic() of last valid frame
        self._interval_deadline: float = 0.0

    # ── lifecycle ──────────────────────────────────────────────────────────

    def start(self) -> None:
        self._interval_deadline = time.monotonic() + INTERVAL_S
        self._task = asyncio.create_task(
            self._run(), name=f"stream-metrics-{self.cam_id}"
        )

    def stop(self) -> None:
        if self._task:
            self._task.cancel()

    # ── connection loop ────────────────────────────────────────────────────

    async def _run(self) -> None:
        backoff_idx = 0
        while True:
            try:
                await self._connect_and_read()
                backoff_idx = 0
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                delay = _BACKOFF[min(backoff_idx, len(_BACKOFF) - 1)]
                log.warning(
                    "stream-metrics %s: %s – reconnecting in %ds",
                    self.cam_id, exc, delay,
                )
                self.state = "disconnected"
                backoff_idx += 1
                await asyncio.sleep(delay)

    async def _connect_and_read(self) -> None:
        # read=15s: if µStreamer stops sending for 15 s, raise and trigger reconnect.
        # At 30 fps we normally receive data every ~33 ms.
        timeout = httpx.Timeout(connect=5.0, read=15.0, write=5.0, pool=5.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            async with client.stream("GET", self.url) as resp:
                resp.raise_for_status()
                log.info("stream-metrics %s: connected", self.cam_id)
                await self._parse_stream(resp)

    # ── multipart MIME parser ──────────────────────────────────────────────

    async def _parse_stream(self, resp: httpx.Response) -> None:
        """Read the multipart stream line by line and dispatch each MIME part."""
        headers: dict[str, str] = {}
        async for raw in resp.aiter_lines():
            # Flush the current interval bucket if the deadline has passed
            now = time.monotonic()
            if now >= self._interval_deadline:
                self._flush_interval(now)

            line = raw.strip()

            if not line:
                # Empty line = end of MIME part headers → process frame
                if headers:
                    self._process_frame(headers)
                    headers = {}

            elif line.startswith("--"):
                # MIME boundary = start of new part
                headers = {}

            elif ":" in line:
                key, _, val = line.partition(":")
                headers[key.strip()] = val.strip()

    # ── frame processing ───────────────────────────────────────────────────

    def _process_frame(self, hdrs: dict[str, str]) -> None:
        if hdrs.get("X-UStreamer-Online", "").lower() != "true":
            self.state = "offline"
            return

        try:
            lat_ms = float(hdrs["X-UStreamer-Latency"]) * 1000
        except (KeyError, ValueError):
            return
        if lat_ms < 0:
            return

        # Accept both grab-time header variants across µStreamer versions
        grab_raw = (
            hdrs.get("X-UStreamer-Grab-Time")
            or hdrs.get("X-UStreamer-Grab-Begin-Time", "")
        )
        try:
            grab_t = float(grab_raw)
        except (ValueError, TypeError):
            return

        # Reject repeated or out-of-order frames
        if grab_t <= self._last_grab:
            return

        self._last_grab       = grab_t
        self._last_frame_wall = time.monotonic()
        self._pending.append(lat_ms)
        self.state = "live"

    # ── interval aggregation ───────────────────────────────────────────────

    def _flush_interval(self, now: float) -> None:
        self._interval_deadline = now + INTERVAL_S

        # Stale detection
        if self.state == "live" and self._last_frame_wall > 0:
            if now - self._last_frame_wall > STALE_SECS:
                self.state = "stale"

        if not self._pending:
            return   # gap interval — no slot appended

        slot = Slot(
            timestamp=time.time(),
            median_ms=round(statistics.median(self._pending), 1),
            max_ms   =round(max(self._pending), 1),
            count    =len(self._pending),
        )
        self.history.append(slot)
        self.latest = slot
        self._pending.clear()

    # ── read-only snapshot for the API ─────────────────────────────────────

    @property
    def snapshot(self) -> dict[str, Any]:
        return {
            "state":   self.state,
            "latest":  self.latest.to_dict() if self.latest else None,
            "history": [s.to_dict() for s in self.history],
        }


# ── Module-level registry ─────────────────────────────────────────────────────

_collectors: dict[str, CameraCollector] = {}


def start_collectors(camera_base_urls: dict[str, str]) -> None:
    """Start one collector per µStreamer-backed camera.

    Parameters
    ----------
    camera_base_urls:
        Mapping of ``cam_id → base URL``, e.g.
        ``{"whiteboard": "http://127.0.0.1:8101"}``.
    """
    for cam_id, base_url in camera_base_urls.items():
        url = f"{base_url}/?action=stream&extra_headers=1&zero_data=1"
        col = CameraCollector(cam_id, url)
        col.start()
        _collectors[cam_id] = col
        log.info("stream-metrics: collector started for %s → %s", cam_id, url)


def stop_collectors() -> None:
    """Cancel all collector tasks and clear the registry."""
    for col in _collectors.values():
        col.stop()
    _collectors.clear()


def get_metrics() -> dict[str, Any]:
    """Return the current metrics snapshot (non-blocking, reads only in-memory data)."""
    return {
        "metric":           "capture_to_send",
        "unit":             "ms",
        "interval_seconds": INTERVAL_S,
        "cameras":          {k: v.snapshot for k, v in _collectors.items()},
    }
