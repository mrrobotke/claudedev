# tests/test_hooks_api.py
"""Tests for hook API endpoints."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import fastapi
import fastapi.responses
import pytest
from httpx import ASGITransport, AsyncClient

from claudedev.api.hooks import create_hooks_router
from claudedev.engines.steering_manager import DirectiveType, SteeringManager

if TYPE_CHECKING:
    from collections.abc import AsyncIterator


@pytest.fixture
def steering() -> SteeringManager:
    sm = SteeringManager()
    sm.register_session("test-session")
    return sm


TEST_HOOK_SECRET = "test-hook-secret"


@pytest.fixture
async def hooks_client(steering: SteeringManager) -> AsyncIterator[AsyncClient]:
    app = fastapi.FastAPI()
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
        hook_output = data["hookSpecificOutput"]
        assert hook_output["hookEventName"] == "PostToolUse"
        assert "Use JWT" in hook_output["additionalContext"]


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
        app = fastapi.FastAPI()
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
        app = fastapi.FastAPI()
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
        app = fastapi.FastAPI()
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
        app = fastapi.FastAPI()
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
        hook_output = data["hookSpecificOutput"]
        assert hook_output["permissionDecision"] == "deny"


class TestWrongSecret:
    """Verify all three hook endpoints reject wrong X-Hook-Secret."""

    @pytest.mark.parametrize(
        "endpoint",
        ["/api/hooks/post-tool-use", "/api/hooks/stop", "/api/hooks/pre-tool-use"],
    )
    async def test_wrong_secret_returns_401(
        self,
        hooks_client: AsyncClient,
        endpoint: str,
    ) -> None:
        resp = await hooks_client.post(
            endpoint,
            json={"tool": "Read"},
            headers={
                "X-Session-Id": "test-session",
                "X-Issue-Number": "42",
                "X-Hook-Secret": "wrong-secret",
            },
        )
        assert resp.status_code == 401
        assert resp.json() == {"error": "Unauthorized"}


def _create_steer_app(steering: SteeringManager) -> fastapi.FastAPI:
    """Build a minimal FastAPI app with just the steer endpoint for testing."""
    app = fastapi.FastAPI()
    app.state.steering_manager = steering

    @app.post("/api/sessions/{session_id}/steer")
    async def steer_session(
        session_id: str, request: fastapi.Request
    ) -> fastapi.responses.JSONResponse:
        body: dict[str, Any] = await request.json()
        message = body.get("message", "")
        directive_type = body.get("directive_type", "inform")
        sm = request.app.state.steering_manager
        try:
            dt = DirectiveType(directive_type)
        except ValueError:
            return fastapi.responses.JSONResponse(
                {"error": f"Invalid directive_type: {directive_type}"}, status_code=400
            )
        try:
            await sm.enqueue_message(session_id, message, dt)
        except KeyError:
            return fastapi.responses.JSONResponse(
                {"error": f"Session {session_id} not registered"}, status_code=404
            )
        return fastapi.responses.JSONResponse({"status": "enqueued"}, status_code=202)

    return app


class TestSteerEndpoint:
    """Tests for POST /api/sessions/{session_id}/steer."""

    @pytest.fixture
    async def steer_client(self, steering: SteeringManager) -> AsyncIterator[AsyncClient]:
        app = _create_steer_app(steering)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac

    async def test_enqueues_message(
        self,
        steer_client: AsyncClient,
        steering: SteeringManager,
    ) -> None:
        resp = await steer_client.post(
            "/api/sessions/test-session/steer",
            json={"message": "Switch to JWT auth", "directive_type": "pivot"},
        )
        assert resp.status_code == 202
        assert resp.json() == {"status": "enqueued"}
        directive = await steering.get_pending_directive("test-session")
        assert directive is not None
        assert directive.message == "Switch to JWT auth"
        assert directive.directive_type == DirectiveType.PIVOT

    async def test_default_directive_type(
        self,
        steer_client: AsyncClient,
        steering: SteeringManager,
    ) -> None:
        resp = await steer_client.post(
            "/api/sessions/test-session/steer",
            json={"message": "FYI: new requirement"},
        )
        assert resp.status_code == 202
        directive = await steering.get_pending_directive("test-session")
        assert directive is not None
        assert directive.directive_type == DirectiveType.INFORM

    async def test_invalid_directive_type_returns_400(
        self,
        steer_client: AsyncClient,
    ) -> None:
        resp = await steer_client.post(
            "/api/sessions/test-session/steer",
            json={"message": "test", "directive_type": "invalid_type"},
        )
        assert resp.status_code == 400
        assert "Invalid directive_type" in resp.json()["error"]

    async def test_unregistered_session_returns_404(
        self,
        steer_client: AsyncClient,
    ) -> None:
        resp = await steer_client.post(
            "/api/sessions/nonexistent-session/steer",
            json={"message": "hello", "directive_type": "inform"},
        )
        assert resp.status_code == 404
        assert "not registered" in resp.json()["error"]
