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


def create_hooks_router(steering: SteeringManager, hook_secret: str = "") -> APIRouter:
    """Create a FastAPI router with hook endpoints."""
    router = APIRouter(prefix="/api/hooks", tags=["hooks"])

    def _check_secret(x_hook_secret: str) -> bool:
        import secrets as _secrets

        if not hook_secret:
            return False  # Reject all if secret not configured
        return _secrets.compare_digest(x_hook_secret, hook_secret)

    @router.post("/post-tool-use")
    async def post_tool_use(
        request: Request,
        x_session_id: str = Header(""),
        x_issue_number: str = Header(""),
        x_hook_secret: str = Header(""),
    ) -> JSONResponse:
        if not _check_secret(x_hook_secret):
            return JSONResponse({"error": "Unauthorized"}, status_code=401)
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
        x_hook_secret: str = Header(""),
    ) -> JSONResponse:
        if not _check_secret(x_hook_secret):
            return JSONResponse({"error": "Unauthorized"}, status_code=401)
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
        x_hook_secret: str = Header(""),
    ) -> JSONResponse:
        if not _check_secret(x_hook_secret):
            return JSONResponse({"error": "Unauthorized"}, status_code=401)
        if not x_session_id:
            logger.warning("hook_missing_session_id", endpoint="pre-tool-use")
            return JSONResponse({})
        body: dict[str, Any] = await request.json()
        result = await steering.handle_pre_tool_use(x_session_id, body)
        return JSONResponse(result)

    return router
