# src/claudedev/engines/websocket_manager.py
"""WebSocket subscriber management and broadcast for live session streaming."""

from __future__ import annotations

import json
from collections import deque
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from starlette.websockets import WebSocket

logger = structlog.get_logger(__name__)

_MAX_BUFFER_SIZE = 100


class WebSocketManager:
    """Manages WebSocket connections and broadcasts session output."""

    def __init__(self) -> None:
        self._subscribers: dict[str, set[WebSocket]] = {}
        self._output_buffers: dict[str, deque[str]] = {}

    async def register_subscriber(self, session_id: str, ws: WebSocket) -> None:
        if session_id not in self._subscribers:
            self._subscribers[session_id] = set()
        self._subscribers[session_id].add(ws)

    async def unregister_subscriber(self, session_id: str, ws: WebSocket) -> None:
        subs = self._subscribers.get(session_id)
        if subs:
            subs.discard(ws)
            if not subs:
                del self._subscribers[session_id]

    def get_subscriber_count(self, session_id: str) -> int:
        return len(self._subscribers.get(session_id, set()))

    async def _broadcast(self, session_id: str, msg: str) -> None:
        """Send msg to all subscribers, removing dead connections."""
        subs = self._subscribers.get(session_id)
        if not subs:
            return
        dead: list[WebSocket] = []
        for ws in subs:
            try:
                await ws.send_text(msg)
            except Exception:
                dead.append(ws)
                logger.warning("ws_subscriber_removed", session_id=session_id, reason="send_failed")
        for ws in dead:
            subs.discard(ws)
        if not subs:
            del self._subscribers[session_id]

    def cleanup_session(self, session_id: str) -> None:
        """Remove all subscriber and buffer state for a session."""
        self._subscribers.pop(session_id, None)
        self._output_buffers.pop(session_id, None)

    async def broadcast_output(self, session_id: str, line: str) -> None:
        if session_id not in self._output_buffers:
            self._output_buffers[session_id] = deque(maxlen=_MAX_BUFFER_SIZE)
        self._output_buffers[session_id].append(line)

        msg = json.dumps(
            {
                "type": "output",
                "data": line,
                "timestamp": datetime.now(UTC).isoformat(),
            }
        )
        await self._broadcast(session_id, msg)

    async def broadcast_activity(
        self,
        session_id: str,
        event_type: str,
        data: dict[str, Any],
    ) -> None:
        msg = json.dumps(
            {
                "type": "activity",
                "event_type": event_type,
                "data": data,
                "timestamp": datetime.now(UTC).isoformat(),
            }
        )
        await self._broadcast(session_id, msg)

    async def broadcast_steering_ack(
        self,
        session_id: str,
        message: str,
        directive_type: str,
    ) -> None:
        """Broadcast a steering acknowledgment to session subscribers."""
        msg = json.dumps(
            {
                "type": "steering_ack",
                "data": {"message": message, "directive_type": directive_type},
                "timestamp": datetime.now(UTC).isoformat(),
            }
        )
        await self._broadcast(session_id, msg)

    def get_output_buffer(self, session_id: str) -> list[str]:
        buf = self._output_buffers.get(session_id)
        return list(buf) if buf else []
