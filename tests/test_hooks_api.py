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


TEST_HOOK_SECRET = "test-hook-secret"


@pytest.fixture
async def hooks_client(steering: SteeringManager):
    from fastapi import FastAPI

    app = FastAPI()
    app.include_router(create_hooks_router(steering, hook_secret=TEST_HOOK_SECRET))
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


class TestPostToolUseEndpoint:
    async def test_no_directive_returns_empty(self, hooks_client: AsyncClient) -> None:
        resp = await hooks_client.post(
            "/api/hooks/post-tool-use",
            json={"tool": "Read"},
            headers={
                "X-Session-Id": "test-session",
                "X-Issue-Number": "42",
                "X-Hook-Secret": TEST_HOOK_SECRET,
            },
        )
        assert resp.status_code == 200
        assert resp.json() == {}

    async def test_with_directive_returns_context(
        self,
        hooks_client: AsyncClient,
        steering: SteeringManager,
    ) -> None:
        await steering.enqueue_message("test-session", "Use JWT", DirectiveType.PIVOT)
        resp = await hooks_client.post(
            "/api/hooks/post-tool-use",
            json={"tool": "Read"},
            headers={
                "X-Session-Id": "test-session",
                "X-Issue-Number": "42",
                "X-Hook-Secret": TEST_HOOK_SECRET,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "additionalContext" in data
        assert "Use JWT" in data["additionalContext"]


class TestStopEndpoint:
    async def test_no_directive_approves(self, hooks_client: AsyncClient) -> None:
        resp = await hooks_client.post(
            "/api/hooks/stop",
            json={},
            headers={
                "X-Session-Id": "test-session",
                "X-Issue-Number": "42",
                "X-Hook-Secret": TEST_HOOK_SECRET,
            },
        )
        assert resp.status_code == 200
        assert resp.json()["decision"] == "approve"

    async def test_pivot_blocks(
        self,
        hooks_client: AsyncClient,
        steering: SteeringManager,
    ) -> None:
        await steering.enqueue_message("test-session", "Change approach", DirectiveType.PIVOT)
        resp = await hooks_client.post(
            "/api/hooks/stop",
            json={},
            headers={
                "X-Session-Id": "test-session",
                "X-Issue-Number": "42",
                "X-Hook-Secret": TEST_HOOK_SECRET,
            },
        )
        data = resp.json()
        assert data["decision"] == "block"


class TestMissingSessionId:
    async def test_stop_missing_session_id_returns_approve(
        self,
        hooks_client: AsyncClient,
    ) -> None:
        """Stop endpoint with missing session_id should return approve decision."""
        resp = await hooks_client.post(
            "/api/hooks/stop",
            json={},
            headers={"X-Session-Id": "", "X-Issue-Number": "42", "X-Hook-Secret": TEST_HOOK_SECRET},
        )
        assert resp.status_code == 200
        assert resp.json()["decision"] == "approve"

    async def test_pre_tool_use_missing_session_id_returns_empty(
        self,
        hooks_client: AsyncClient,
    ) -> None:
        """Pre-tool-use endpoint with missing session_id should return empty JSON."""
        resp = await hooks_client.post(
            "/api/hooks/pre-tool-use",
            json={"tool": "Edit"},
            headers={"X-Session-Id": "", "X-Issue-Number": "42", "X-Hook-Secret": TEST_HOOK_SECRET},
        )
        assert resp.status_code == 200
        assert resp.json() == {}


class TestHookSecretValidation:
    """Verify that hook_secret configuration enforces authentication correctly."""

    async def test_no_secret_configured_rejects_all(self, steering: SteeringManager) -> None:
        """When hook_secret is empty, ALL requests must be rejected with 401."""
        from fastapi import FastAPI

        app = FastAPI()
        app.include_router(create_hooks_router(steering, hook_secret=""))
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            for endpoint in (
                "/api/hooks/post-tool-use",
                "/api/hooks/stop",
                "/api/hooks/pre-tool-use",
            ):
                resp = await client.post(endpoint, json={})
                assert resp.status_code == 401, (
                    f"{endpoint} should be 401 when hook_secret is empty"
                )
                assert resp.json() == {"error": "Unauthorized"}

    async def test_configured_secret_missing_header_returns_401(
        self,
        steering: SteeringManager,
    ) -> None:
        """Requests without X-Hook-Secret header are rejected when secret is configured."""
        from fastapi import FastAPI

        app = FastAPI()
        app.include_router(create_hooks_router(steering, hook_secret="correct-secret"))
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/hooks/stop",
                json={},
                headers={"X-Session-Id": "test-session"},
            )
            assert resp.status_code == 401
            assert resp.json() == {"error": "Unauthorized"}

    async def test_configured_secret_wrong_value_returns_401(
        self,
        steering: SteeringManager,
    ) -> None:
        """Requests with wrong X-Hook-Secret are rejected when secret is configured."""
        from fastapi import FastAPI

        app = FastAPI()
        app.include_router(create_hooks_router(steering, hook_secret="correct-secret"))
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/hooks/stop",
                json={},
                headers={"X-Session-Id": "test-session", "X-Hook-Secret": "wrong-secret"},
            )
            assert resp.status_code == 401
            assert resp.json() == {"error": "Unauthorized"}

    async def test_configured_secret_correct_value_succeeds(
        self,
        steering: SteeringManager,
    ) -> None:
        """Requests with correct X-Hook-Secret succeed when secret is configured."""
        from fastapi import FastAPI

        app = FastAPI()
        app.include_router(create_hooks_router(steering, hook_secret="correct-secret"))
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/hooks/stop",
                json={},
                headers={"X-Session-Id": "test-session", "X-Hook-Secret": "correct-secret"},
            )
            assert resp.status_code == 200
            assert resp.json()["decision"] == "approve"


class TestPreToolUseEndpoint:
    async def test_no_abort_allows(self, hooks_client: AsyncClient) -> None:
        resp = await hooks_client.post(
            "/api/hooks/pre-tool-use",
            json={"tool": "Edit"},
            headers={
                "X-Session-Id": "test-session",
                "X-Issue-Number": "42",
                "X-Hook-Secret": TEST_HOOK_SECRET,
            },
        )
        assert resp.status_code == 200
        assert resp.json() == {}

    async def test_abort_denies(
        self,
        hooks_client: AsyncClient,
        steering: SteeringManager,
    ) -> None:
        await steering.enqueue_message("test-session", "Stop", DirectiveType.ABORT)
        resp = await hooks_client.post(
            "/api/hooks/pre-tool-use",
            json={"tool": "Edit"},
            headers={
                "X-Session-Id": "test-session",
                "X-Issue-Number": "42",
                "X-Hook-Secret": TEST_HOOK_SECRET,
            },
        )
        data = resp.json()
        assert data["permissionDecision"] == "deny"
