# tests/test_hooks_api.py
"""Tests for hook API endpoints."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from claudedev.api.hooks import create_hooks_router
from claudedev.engines.steering_manager import DirectiveType, SteeringManager


@pytest.fixture
def steering() -> SteeringManager:
    sm = SteeringManager()
    sm.register_session("test-session")
    return sm


@pytest.fixture
async def hooks_client(steering: SteeringManager):
    from fastapi import FastAPI
    app = FastAPI()
    app.include_router(create_hooks_router(steering))
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


class TestPostToolUseEndpoint:
    async def test_no_directive_returns_empty(self, hooks_client: AsyncClient) -> None:
        resp = await hooks_client.post(
            "/api/hooks/post-tool-use",
            json={"tool": "Read"},
            headers={"X-Session-Id": "test-session", "X-Issue-Number": "42"},
        )
        assert resp.status_code == 200
        assert resp.json() == {}

    async def test_with_directive_returns_context(
        self, hooks_client: AsyncClient, steering: SteeringManager,
    ) -> None:
        await steering.enqueue_message("test-session", "Use JWT", DirectiveType.PIVOT)
        resp = await hooks_client.post(
            "/api/hooks/post-tool-use",
            json={"tool": "Read"},
            headers={"X-Session-Id": "test-session", "X-Issue-Number": "42"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "additionalContext" in data
        assert "Use JWT" in data["additionalContext"]


class TestStopEndpoint:
    async def test_no_directive_approves(self, hooks_client: AsyncClient) -> None:
        resp = await hooks_client.post(
            "/api/hooks/stop", json={},
            headers={"X-Session-Id": "test-session", "X-Issue-Number": "42"},
        )
        assert resp.status_code == 200
        assert resp.json()["decision"] == "approve"

    async def test_pivot_blocks(
        self, hooks_client: AsyncClient, steering: SteeringManager,
    ) -> None:
        await steering.enqueue_message("test-session", "Change approach", DirectiveType.PIVOT)
        resp = await hooks_client.post(
            "/api/hooks/stop", json={},
            headers={"X-Session-Id": "test-session", "X-Issue-Number": "42"},
        )
        data = resp.json()
        assert data["decision"] == "block"


class TestPreToolUseEndpoint:
    async def test_no_abort_allows(self, hooks_client: AsyncClient) -> None:
        resp = await hooks_client.post(
            "/api/hooks/pre-tool-use", json={"tool": "Edit"},
            headers={"X-Session-Id": "test-session", "X-Issue-Number": "42"},
        )
        assert resp.status_code == 200
        assert resp.json() == {}

    async def test_abort_denies(
        self, hooks_client: AsyncClient, steering: SteeringManager,
    ) -> None:
        await steering.enqueue_message("test-session", "Stop", DirectiveType.ABORT)
        resp = await hooks_client.post(
            "/api/hooks/pre-tool-use", json={"tool": "Edit"},
            headers={"X-Session-Id": "test-session", "X-Issue-Number": "42"},
        )
        data = resp.json()
        assert data["permissionDecision"] == "deny"
