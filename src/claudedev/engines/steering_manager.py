# src/claudedev/engines/steering_manager.py
"""Per-session directive queues and hook response logic for human steering."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

import structlog
from pydantic import BaseModel, Field

logger = structlog.get_logger(__name__)


class DirectiveType(StrEnum):
    PIVOT = "pivot"
    CONSTRAIN = "constrain"
    INFORM = "inform"
    ABORT = "abort"


class SteeringDirective(BaseModel):
    """A human steering message for an active implementation session."""

    session_id: str
    message: str
    directive_type: DirectiveType
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    acknowledged: bool = False


class ActivityEvent(BaseModel):
    """A recorded hook invocation or steering event."""

    session_id: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    event_type: str
    tool_name: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class SteeringManager:
    """Manages per-session steering message queues and hook responses."""

    def __init__(self) -> None:
        self._queues: dict[str, asyncio.Queue[SteeringDirective]] = {}
        self._activity: dict[str, list[ActivityEvent]] = {}
        self._stop_hook_active: dict[str, bool] = {}

    def register_session(self, session_id: str) -> None:
        if session_id not in self._queues:
            self._queues[session_id] = asyncio.Queue()
            self._activity[session_id] = []
            self._stop_hook_active[session_id] = False

    def unregister_session(self, session_id: str) -> None:
        self._queues.pop(session_id, None)
        self._activity.pop(session_id, None)
        self._stop_hook_active.pop(session_id, None)

    def is_session_active(self, session_id: str) -> bool:
        return session_id in self._queues

    async def enqueue_message(
        self, session_id: str, message: str, directive_type: DirectiveType,
    ) -> None:
        if session_id not in self._queues:
            raise KeyError(f"Session {session_id} not registered")
        directive = SteeringDirective(
            session_id=session_id, message=message, directive_type=directive_type,
        )
        await self._queues[session_id].put(directive)

    async def get_pending_directive(self, session_id: str) -> SteeringDirective | None:
        queue = self._queues.get(session_id)
        if queue is None:
            return None
        try:
            return queue.get_nowait()
        except asyncio.QueueEmpty:
            return None

    async def handle_post_tool_use(
        self, session_id: str, hook_payload: dict[str, Any],
    ) -> dict[str, Any]:
        tool_name = hook_payload.get("tool", "unknown")
        self._log_activity(session_id, "tool_use", tool_name=tool_name)

        directive = await self.get_pending_directive(session_id)
        if directive is None:
            return {}

        directive.acknowledged = True
        self._log_activity(
            session_id, "steering_sent",
            details={"message": directive.message, "type": directive.directive_type.value},
        )
        context = (
            f"[CLAUDEDEV STEERING - {directive.directive_type.value.upper()}]\n"
            f"From the project owner: {directive.message}\n"
            f"You MUST acknowledge this directive and adjust your approach accordingly."
        )
        return {"additionalContext": context}

    async def handle_stop(
        self, session_id: str, hook_payload: dict[str, Any],
    ) -> dict[str, Any]:
        if self._stop_hook_active.get(session_id, False):
            self._stop_hook_active[session_id] = False
            return {"decision": "approve"}

        directive = await self.get_pending_directive(session_id)
        if directive is None:
            return {"decision": "approve"}

        if directive.directive_type == DirectiveType.ABORT:
            self._log_activity(session_id, "abort")
            return {"decision": "approve"}

        self._stop_hook_active[session_id] = True
        self._log_activity(
            session_id, "steering_sent",
            details={"message": directive.message, "type": directive.directive_type.value},
        )
        reason = (
            f"[CLAUDEDEV STEERING - {directive.directive_type.value.upper()}]\n"
            f"From the project owner: {directive.message}\n"
            f"Continue working and adjust your approach accordingly."
        )
        return {"decision": "block", "reason": reason}

    async def handle_pre_tool_use(
        self, session_id: str, hook_payload: dict[str, Any],
    ) -> dict[str, Any]:
        queue = self._queues.get(session_id)
        if queue is None:
            return {}
        try:
            directive = queue.get_nowait()
        except asyncio.QueueEmpty:
            return {}

        if directive.directive_type == DirectiveType.ABORT:
            self._log_activity(session_id, "abort")
            return {
                "permissionDecision": "deny",
                "reason": "Implementation aborted by project owner",
            }
        # Not abort — put it back
        await queue.put(directive)
        return {}

    def get_session_activity(self, session_id: str) -> list[ActivityEvent]:
        return self._activity.get(session_id, [])

    def _log_activity(
        self, session_id: str, event_type: str,
        tool_name: str | None = None, details: dict[str, Any] | None = None,
    ) -> None:
        if session_id not in self._activity:
            return
        event = ActivityEvent(
            session_id=session_id, event_type=event_type,
            tool_name=tool_name, details=details or {},
        )
        self._activity[session_id].append(event)
        logger.debug(
            "activity_logged",
            session_id=session_id,
            event_type=event_type,
            tool_name=tool_name,
        )
