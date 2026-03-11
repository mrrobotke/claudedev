# tests/test_live_session.py
"""Tests for live session page and WebSocket endpoints."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from claudedev.engines.steering_manager import SteeringManager
from claudedev.engines.websocket_manager import WebSocketManager
from claudedev.ui.live_session import LIVE_SESSION_HTML, create_live_session_router


class TestLiveSessionPage:
    async def test_serves_html(self) -> None:
        from fastapi import FastAPI

        app = FastAPI()
        app.include_router(create_live_session_router(WebSocketManager(), SteeringManager()))
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/session/test-123/live")
            assert resp.status_code == 200
            assert "Live Session" in resp.text

    async def test_session_id_in_html(self) -> None:
        from fastapi import FastAPI

        app = FastAPI()
        app.include_router(create_live_session_router(WebSocketManager(), SteeringManager()))
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/session/my-session-42/live")
            assert "my-session-42" in resp.text

    async def test_html_content_type(self) -> None:
        from fastapi import FastAPI

        app = FastAPI()
        app.include_router(create_live_session_router(WebSocketManager(), SteeringManager()))
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/session/test/live")
            assert "text/html" in resp.headers["content-type"]


class TestLiveSessionValidation:
    async def test_invalid_session_id_returns_400(self) -> None:
        """Session IDs with special characters should be rejected with 400.

        Uses characters that are URL-safe (pass routing) but rejected by the
        server-side [a-zA-Z0-9_-] regex to prevent XSS in the JS context.
        """
        from fastapi import FastAPI

        app = FastAPI()
        app.include_router(create_live_session_router(WebSocketManager(), SteeringManager()))
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # Dots and at-signs pass URL routing but fail the alphanumeric+dash+underscore regex
            resp = await client.get("/session/bad.session@id/live")
            assert resp.status_code == 400


class TestLiveSessionHTML:
    def test_html_template_has_placeholder(self) -> None:
        assert "{session_id}" in LIVE_SESSION_HTML

    def test_html_uses_textcontent(self) -> None:
        """Verify XSS-safe rendering via textContent, not innerHTML."""
        assert "textContent" in LIVE_SESSION_HTML
        # innerHTML should only appear in non-user-data contexts
        assert "innerHTML" not in LIVE_SESSION_HTML

    def test_html_has_websocket_paths(self) -> None:
        assert "/ws/session/" in LIVE_SESSION_HTML
        assert "/stream" in LIVE_SESSION_HTML
        assert "/steer" in LIVE_SESSION_HTML


class TestWebSocketStreamEndpoint:
    async def test_stream_ws_accepts_connection(self) -> None:
        """WS /ws/session/{id}/stream accepts and registers subscriber."""
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        ws_mgr = WebSocketManager()
        sm = SteeringManager()
        sm.register_session("test-ws")
        app = FastAPI()
        app.include_router(create_live_session_router(ws_mgr, sm))

        client = TestClient(app)
        with client.websocket_connect("/ws/session/test-ws/stream"):
            assert ws_mgr.get_subscriber_count("test-ws") == 1

    async def test_stream_rejects_unregistered_session(self) -> None:
        """WS /ws/session/{id}/stream rejects connection when session not registered."""
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from starlette.websockets import WebSocketDisconnect

        ws_mgr = WebSocketManager()
        sm = SteeringManager()
        # Do NOT register "unknown-session"
        app = FastAPI()
        app.include_router(create_live_session_router(ws_mgr, sm))

        client = TestClient(app)
        with (
            pytest.raises(WebSocketDisconnect) as exc_info,
            client.websocket_connect("/ws/session/unknown-session/stream"),
        ):
            pass
        assert exc_info.value.code == 4003

    async def test_stream_cleanup_on_disconnect(self) -> None:
        """Subscriber is removed from WebSocketManager after disconnect."""
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        ws_mgr = WebSocketManager()
        sm = SteeringManager()
        sm.register_session("cleanup-test")
        app = FastAPI()
        app.include_router(create_live_session_router(ws_mgr, sm))

        client = TestClient(app)
        with client.websocket_connect("/ws/session/cleanup-test/stream"):
            assert ws_mgr.get_subscriber_count("cleanup-test") == 1
        # After disconnect, subscriber should be cleaned up
        assert ws_mgr.get_subscriber_count("cleanup-test") == 0


class TestWebSocketSteerEndpoint:
    async def test_steer_ws_enqueues_directive(self) -> None:
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        ws_mgr = WebSocketManager()
        sm = SteeringManager()
        sm.register_session("test-steer")
        app = FastAPI()
        app.include_router(create_live_session_router(ws_mgr, sm))

        client = TestClient(app)
        with client.websocket_connect("/ws/session/test-steer/steer") as ws:
            ws.send_json({"message": "Use Redis", "directive_type": "pivot"})
            resp = ws.receive_json()
            assert resp["status"] == "queued"
            assert resp["directive_type"] == "pivot"

    async def test_steer_rejects_unregistered_session(self) -> None:
        """WS /ws/session/{id}/steer rejects connection when session not registered."""
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from starlette.websockets import WebSocketDisconnect

        ws_mgr = WebSocketManager()
        sm = SteeringManager()
        # Do NOT register "unknown-session"
        app = FastAPI()
        app.include_router(create_live_session_router(ws_mgr, sm))

        client = TestClient(app)
        with (
            pytest.raises(WebSocketDisconnect) as exc_info,
            client.websocket_connect("/ws/session/unknown-session/steer"),
        ):
            pass
        assert exc_info.value.code == 4003
