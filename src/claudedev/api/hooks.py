# src/claudedev/api/hooks.py
"""Hook API endpoints for Claude Code steering integration."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog
from fastapi import APIRouter, Header, Request
from fastapi.responses import JSONResponse

if TYPE_CHECKING:
    from claudedev.engines.steering_manager import SteeringManager

logger = structlog.get_logger(__name__)


def create_hooks_router(steering: SteeringManager) -> APIRouter:
    """Create a FastAPI router with hook endpoints."""
    router = APIRouter(prefix="/api/hooks", tags=["hooks"])

    @router.post("/post-tool-use")
    async def post_tool_use(
        request: Request,
        x_session_id: str = Header(""),
        x_issue_number: str = Header(""),
    ) -> JSONResponse:
        if not x_session_id:
            logger.warning("hook_missing_session_id", endpoint="post-tool-use")
            return JSONResponse({})
        body: dict[str, Any] = await request.json()
        result = await steering.handle_post_tool_use(x_session_id, body)
        return JSONResponse(result)

    @router.post("/stop")
    async def stop(
        request: Request,
        x_session_id: str = Header(""),
        x_issue_number: str = Header(""),
    ) -> JSONResponse:
        if not x_session_id:
            logger.warning("hook_missing_session_id", endpoint="stop")
            return JSONResponse({"decision": "approve"})
        body: dict[str, Any] = await request.json()
        result = await steering.handle_stop(x_session_id, body)
        return JSONResponse(result)

    @router.post("/pre-tool-use")
    async def pre_tool_use(
        request: Request,
        x_session_id: str = Header(""),
        x_issue_number: str = Header(""),
    ) -> JSONResponse:
        if not x_session_id:
            logger.warning("hook_missing_session_id", endpoint="pre-tool-use")
            return JSONResponse({})
        body: dict[str, Any] = await request.json()
        result = await steering.handle_pre_tool_use(x_session_id, body)
        return JSONResponse(result)

    return router
