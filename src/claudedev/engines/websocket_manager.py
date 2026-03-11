# src/claudedev/engines/websocket_manager.py
"""WebSocket subscriber management and broadcast for live session streaming."""

from __future__ import annotations

import json
from collections import deque
from datetime import UTC, datetime
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

_MAX_BUFFER_SIZE = 100


class WebSocketManager:
    """Manages WebSocket connections and broadcasts session output."""

    def __init__(self) -> None:
        self._subscribers: dict[str, set[Any]] = {}
        self._output_buffers: dict[str, deque[str]] = {}

    async def register_subscriber(self, session_id: str, ws: Any) -> None:
        if session_id not in self._subscribers:
            self._subscribers[session_id] = set()
        self._subscribers[session_id].add(ws)

    async def unregister_subscriber(self, session_id: str, ws: Any) -> None:
        subs = self._subscribers.get(session_id)
        if subs:
            subs.discard(ws)

    def get_subscriber_count(self, session_id: str) -> int:
        return len(self._subscribers.get(session_id, set()))

    async def broadcast_output(self, session_id: str, line: str) -> None:
        if session_id not in self._output_buffers:
            self._output_buffers[session_id] = deque(maxlen=_MAX_BUFFER_SIZE)
        self._output_buffers[session_id].append(line)

        subs = self._subscribers.get(session_id)
        if not subs:
            return

        msg = json.dumps({
            "type": "output", "data": line,
            "timestamp": datetime.now(UTC).isoformat(),
        })

        dead: list[Any] = []
        for ws in subs:
            try:
                await ws.send_text(msg)
            except Exception:
                dead.append(ws)
        for ws in dead:
            subs.discard(ws)

    async def broadcast_activity(
        self, session_id: str, event_type: str, data: dict[str, Any],
    ) -> None:
        subs = self._subscribers.get(session_id)
        if not subs:
            return
        msg = json.dumps({
            "type": "activity", "data": data,
            "timestamp": datetime.now(UTC).isoformat(),
        })
        dead: list[Any] = []
        for ws in subs:
            try:
                await ws.send_text(msg)
            except Exception:
                dead.append(ws)
        for ws in dead:
            subs.discard(ws)

    async def broadcast_steering_ack(
        self, session_id: str, message: str, directive_type: str,
    ) -> None:
        """Broadcast a steering acknowledgment to session subscribers."""
        subs = self._subscribers.get(session_id)
        if not subs:
            return
        msg = json.dumps({
            "type": "steering_ack",
            "data": {"message": message, "directive_type": directive_type},
            "timestamp": datetime.now(UTC).isoformat(),
        })
        dead: list[Any] = []
        for ws in subs:
            try:
                await ws.send_text(msg)
            except Exception:
                dead.append(ws)
        for ws in dead:
            subs.discard(ws)

    def get_output_buffer(self, session_id: str) -> list[str]:
        buf = self._output_buffers.get(session_id)
        return list(buf) if buf else []
