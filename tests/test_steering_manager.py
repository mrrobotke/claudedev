# tests/test_steering_manager.py
"""Tests for SteeringManager — per-session directive queues."""

from __future__ import annotations

import pytest

from claudedev.engines.steering_manager import (
    DirectiveType,
    SteeringManager,
)


@pytest.fixture
def sm() -> SteeringManager:
    return SteeringManager()


class TestSessionLifecycle:
    async def test_register_and_unregister(self, sm: SteeringManager) -> None:
        sm.register_session("s1")
        assert sm.is_session_active("s1")
        sm.unregister_session("s1")
        assert not sm.is_session_active("s1")

    async def test_unregister_nonexistent_is_safe(self, sm: SteeringManager) -> None:
        sm.unregister_session("nonexistent")

    async def test_register_idempotent(self, sm: SteeringManager) -> None:
        sm.register_session("s1")
        sm.register_session("s1")
        assert sm.is_session_active("s1")


class TestDirectiveQueue:
    async def test_enqueue_and_get(self, sm: SteeringManager) -> None:
        sm.register_session("s1")
        await sm.enqueue_message("s1", "Use Redis", DirectiveType.PIVOT)
        directive = await sm.get_pending_directive("s1")
        assert directive is not None
        assert directive.message == "Use Redis"
        assert directive.directive_type == DirectiveType.PIVOT

    async def test_get_empty_returns_none(self, sm: SteeringManager) -> None:
        sm.register_session("s1")
        directive = await sm.get_pending_directive("s1")
        assert directive is None

    async def test_fifo_ordering(self, sm: SteeringManager) -> None:
        sm.register_session("s1")
        await sm.enqueue_message("s1", "first", DirectiveType.INFORM)
        await sm.enqueue_message("s1", "second", DirectiveType.CONSTRAIN)
        d1 = await sm.get_pending_directive("s1")
        d2 = await sm.get_pending_directive("s1")
        assert d1 is not None and d1.message == "first"
        assert d2 is not None and d2.message == "second"

    async def test_enqueue_unregistered_raises(self, sm: SteeringManager) -> None:
        with pytest.raises(KeyError):
            await sm.enqueue_message("bad", "msg", DirectiveType.INFORM)

    async def test_get_unregistered_returns_none(self, sm: SteeringManager) -> None:
        result = await sm.get_pending_directive("bad")
        assert result is None


class TestHookHandlers:
    async def test_post_tool_use_no_directive(self, sm: SteeringManager) -> None:
        sm.register_session("s1")
        result = await sm.handle_post_tool_use("s1", {"tool": "Read"})
        assert result == {}

    async def test_post_tool_use_with_directive(self, sm: SteeringManager) -> None:
        sm.register_session("s1")
        await sm.enqueue_message("s1", "Switch to Redis", DirectiveType.PIVOT)
        result = await sm.handle_post_tool_use("s1", {"tool": "Read"})
        assert "additionalContext" in result
        assert "Switch to Redis" in result["additionalContext"]

    async def test_stop_no_directive_approves(self, sm: SteeringManager) -> None:
        sm.register_session("s1")
        result = await sm.handle_stop("s1", {})
        assert result.get("decision") == "approve"

    async def test_stop_with_abort_approves(self, sm: SteeringManager) -> None:
        sm.register_session("s1")
        await sm.enqueue_message("s1", "Stop now", DirectiveType.ABORT)
        result = await sm.handle_stop("s1", {})
        assert result.get("decision") == "approve"

    async def test_stop_with_pivot_blocks(self, sm: SteeringManager) -> None:
        sm.register_session("s1")
        await sm.enqueue_message("s1", "Try different approach", DirectiveType.PIVOT)
        result = await sm.handle_stop("s1", {})
        assert result.get("decision") == "block"
        assert "Try different approach" in result.get("reason", "")

    async def test_pre_tool_use_no_abort(self, sm: SteeringManager) -> None:
        sm.register_session("s1")
        result = await sm.handle_pre_tool_use("s1", {"tool": "Edit"})
        assert result == {}

    async def test_pre_tool_use_with_abort(self, sm: SteeringManager) -> None:
        sm.register_session("s1")
        await sm.enqueue_message("s1", "Abort", DirectiveType.ABORT)
        result = await sm.handle_pre_tool_use("s1", {"tool": "Edit"})
        assert "permissionDecision" in result
        assert result["permissionDecision"] == "deny"


class TestActivityTracking:
    async def test_hook_invocation_logged(self, sm: SteeringManager) -> None:
        sm.register_session("s1")
        await sm.handle_post_tool_use("s1", {"tool": "Read"})
        activity = sm.get_session_activity("s1")
        assert len(activity) >= 1
        assert activity[0].event_type == "tool_use"

    async def test_steering_delivery_logged(self, sm: SteeringManager) -> None:
        sm.register_session("s1")
        await sm.enqueue_message("s1", "test", DirectiveType.INFORM)
        await sm.handle_post_tool_use("s1", {"tool": "Read"})
        activity = sm.get_session_activity("s1")
        types = [a.event_type for a in activity]
        assert "steering_sent" in types

    async def test_activity_empty_for_unknown_session(self, sm: SteeringManager) -> None:
        result = sm.get_session_activity("unknown")
        assert result == []


class TestSteeringDirectiveValidation:
    """Validate SteeringDirective Pydantic constraints."""

    def test_session_id_rejects_special_chars(self) -> None:
        from pydantic import ValidationError

        from claudedev.engines.steering_manager import SteeringDirective

        with pytest.raises(ValidationError):
            SteeringDirective(session_id="bad@id", message="x", directive_type=DirectiveType.INFORM)

    def test_session_id_rejects_empty(self) -> None:
        from pydantic import ValidationError

        from claudedev.engines.steering_manager import SteeringDirective

        with pytest.raises(ValidationError):
            SteeringDirective(session_id="", message="x", directive_type=DirectiveType.INFORM)

    def test_session_id_rejects_too_long(self) -> None:
        from pydantic import ValidationError

        from claudedev.engines.steering_manager import SteeringDirective

        with pytest.raises(ValidationError):
            SteeringDirective(
                session_id="x" * 129, message="x", directive_type=DirectiveType.INFORM
            )

    def test_session_id_accepts_valid(self) -> None:
        from claudedev.engines.steering_manager import SteeringDirective

        d = SteeringDirective(
            session_id="abc-123_XYZ", message="x", directive_type=DirectiveType.INFORM
        )
        assert d.session_id == "abc-123_XYZ"

    def test_message_max_length_rejected(self) -> None:
        from pydantic import ValidationError

        from claudedev.engines.steering_manager import SteeringDirective

        with pytest.raises(ValidationError):
            SteeringDirective(
                session_id="s1", message="x" * 2001, directive_type=DirectiveType.INFORM
            )

    def test_message_max_length_accepted(self) -> None:
        from claudedev.engines.steering_manager import SteeringDirective

        d = SteeringDirective(
            session_id="s1", message="x" * 2000, directive_type=DirectiveType.INFORM
        )
        assert len(d.message) == 2000


class TestDirectiveTypeUnknown:
    async def test_enqueue_with_unknown_type(self, sm: SteeringManager) -> None:
        sm.register_session("s1")
        await sm.enqueue_message("s1", "test unknown", DirectiveType.UNKNOWN)
        directive = await sm.get_pending_directive("s1")
        assert directive is not None
        assert directive.directive_type == DirectiveType.UNKNOWN


class TestActivityDequeOverflow:
    async def test_deque_capped_at_max_size(self, sm: SteeringManager) -> None:
        sm.register_session("s1")
        for _ in range(550):
            await sm.handle_post_tool_use("s1", {"tool": "Read"})
        activity = sm.get_session_activity("s1")
        assert len(activity) <= 500
