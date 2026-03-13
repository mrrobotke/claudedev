# tests/test_websocket_manager.py
"""Tests for WebSocketManager — session output broadcasting."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest

from claudedev.engines.websocket_manager import WebSocketManager


@pytest.fixture
def ws_manager() -> WebSocketManager:
    return WebSocketManager()


def make_mock_ws() -> AsyncMock:
    ws = AsyncMock()
    ws.send_text = AsyncMock()
    return ws


class TestSubscription:
    async def test_register_subscriber(self, ws_manager: WebSocketManager) -> None:
        ws = make_mock_ws()
        await ws_manager.register_subscriber("s1", ws)
        assert ws_manager.get_subscriber_count("s1") == 1

    async def test_unregister_subscriber(self, ws_manager: WebSocketManager) -> None:
        ws = make_mock_ws()
        await ws_manager.register_subscriber("s1", ws)
        await ws_manager.unregister_subscriber("s1", ws)
        assert ws_manager.get_subscriber_count("s1") == 0

    async def test_multiple_subscribers(self, ws_manager: WebSocketManager) -> None:
        ws1 = make_mock_ws()
        ws2 = make_mock_ws()
        await ws_manager.register_subscriber("s1", ws1)
        await ws_manager.register_subscriber("s1", ws2)
        assert ws_manager.get_subscriber_count("s1") == 2

    async def test_count_unknown_session(self, ws_manager: WebSocketManager) -> None:
        assert ws_manager.get_subscriber_count("unknown") == 0


class TestBroadcast:
    async def test_broadcast_output(self, ws_manager: WebSocketManager) -> None:
        ws = make_mock_ws()
        await ws_manager.register_subscriber("s1", ws)
        await ws_manager.broadcast_output("s1", "Hello world")
        ws.send_text.assert_called_once()
        msg = json.loads(ws.send_text.call_args[0][0])
        assert msg["type"] == "output"
        assert msg["data"] == "Hello world"

    async def test_broadcast_to_multiple(self, ws_manager: WebSocketManager) -> None:
        ws1 = make_mock_ws()
        ws2 = make_mock_ws()
        await ws_manager.register_subscriber("s1", ws1)
        await ws_manager.register_subscriber("s1", ws2)
        await ws_manager.broadcast_output("s1", "test")
        ws1.send_text.assert_called_once()
        ws2.send_text.assert_called_once()

    async def test_broadcast_no_subscribers(self, ws_manager: WebSocketManager) -> None:
        await ws_manager.broadcast_output("none", "test")

    async def test_dead_subscriber_removed(self, ws_manager: WebSocketManager) -> None:
        ws = make_mock_ws()
        ws.send_text.side_effect = Exception("Connection closed")
        await ws_manager.register_subscriber("s1", ws)
        await ws_manager.broadcast_output("s1", "test")
        assert ws_manager.get_subscriber_count("s1") == 0


class TestOutputBuffer:
    async def test_buffer_stores_lines(self, ws_manager: WebSocketManager) -> None:
        await ws_manager.broadcast_output("s1", "line 1")
        await ws_manager.broadcast_output("s1", "line 2")
        buffer = ws_manager.get_output_buffer("s1")
        assert len(buffer) == 2

    async def test_buffer_max_size(self, ws_manager: WebSocketManager) -> None:
        for i in range(150):
            await ws_manager.broadcast_output("s1", f"line {i}")
        buffer = ws_manager.get_output_buffer("s1")
        assert len(buffer) == 100

    async def test_empty_buffer(self, ws_manager: WebSocketManager) -> None:
        buffer = ws_manager.get_output_buffer("unknown")
        assert buffer == []


class TestBroadcastActivity:
    async def test_activity_sent_to_subscribers(self, ws_manager: WebSocketManager) -> None:
        ws = make_mock_ws()
        await ws_manager.register_subscriber("s1", ws)
        await ws_manager.broadcast_activity("s1", "tool_use", {"tool": "Read"})
        ws.send_text.assert_called_once()
        msg = json.loads(ws.send_text.call_args[0][0])
        assert msg["type"] == "activity"
        assert msg["data"]["tool"] == "Read"

    async def test_activity_no_subscribers_safe(self, ws_manager: WebSocketManager) -> None:
        await ws_manager.broadcast_activity("none", "tool_use", {})


class TestBroadcastSteeringAck:
    async def test_steering_ack_sent(self, ws_manager: WebSocketManager) -> None:
        ws = make_mock_ws()
        await ws_manager.register_subscriber("s1", ws)
        await ws_manager.broadcast_steering_ack(
            "s1",
            message="Use Redis",
            directive_type="pivot",
        )
        ws.send_text.assert_called_once()
        msg = json.loads(ws.send_text.call_args[0][0])
        assert msg["type"] == "steering_ack"
        assert msg["data"]["message"] == "Use Redis"
        assert msg["data"]["directive_type"] == "pivot"

    async def test_steering_ack_dead_subscriber_removed(
        self,
        ws_manager: WebSocketManager,
    ) -> None:
        ws = make_mock_ws()
        ws.send_text.side_effect = Exception("closed")
        await ws_manager.register_subscriber("s1", ws)
        await ws_manager.broadcast_steering_ack("s1", message="x", directive_type="inform")
        assert ws_manager.get_subscriber_count("s1") == 0


class TestCleanupSession:
    async def test_cleanup_removes_subscribers(self, ws_manager: WebSocketManager) -> None:
        ws = make_mock_ws()
        await ws_manager.register_subscriber("s1", ws)
        assert ws_manager.get_subscriber_count("s1") == 1
        ws_manager.cleanup_session("s1")
        assert ws_manager.get_subscriber_count("s1") == 0

    async def test_cleanup_unknown_session_safe(self, ws_manager: WebSocketManager) -> None:
        ws_manager.cleanup_session("unknown")  # should not raise

    async def test_unregister_last_subscriber_removes_session_key(
        self,
        ws_manager: WebSocketManager,
    ) -> None:
        """After unregistering the last subscriber, the session key is removed from _subscribers."""
        ws = make_mock_ws()
        await ws_manager.register_subscriber("s1", ws)
        await ws_manager.unregister_subscriber("s1", ws)
        assert "s1" not in ws_manager._subscribers
