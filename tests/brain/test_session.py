"""Tests for Session and SessionManager."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from claudedev.brain.integration.session import Session, SessionManager

# ---------------------------------------------------------------------------
# Session
# ---------------------------------------------------------------------------


class TestSessionCreation:
    def test_create_returns_session(self) -> None:
        session = Session.create()
        assert isinstance(session, Session)

    def test_create_generates_brain_prefixed_id(self) -> None:
        session = Session.create()
        assert session.id.startswith("brain-")

    def test_create_id_has_correct_length(self) -> None:
        session = Session.create()
        # "brain-" (6) + 12 hex chars = 18
        assert len(session.id) == 18

    def test_create_generates_unique_ids(self) -> None:
        ids = {Session.create().id for _ in range(20)}
        assert len(ids) == 20

    def test_init_sets_provided_id(self) -> None:
        session = Session("brain-customid1234")
        assert session.id == "brain-customid1234"

    def test_init_sets_empty_history(self) -> None:
        session = Session("brain-abc123456789")
        assert session.conversation_history == []

    def test_init_sets_created_at_utc(self) -> None:
        before = datetime.now(UTC)
        session = Session.create()
        after = datetime.now(UTC)
        assert before <= session.created_at <= after

    def test_init_sets_last_active_utc(self) -> None:
        before = datetime.now(UTC)
        session = Session.create()
        after = datetime.now(UTC)
        assert before <= session.last_active <= after

    def test_created_at_and_last_active_are_close(self) -> None:
        session = Session.create()
        delta = abs((session.last_active - session.created_at).total_seconds())
        assert delta < 1.0


class TestSessionAddTurn:
    def test_add_turn_appends_to_history(self) -> None:
        session = Session.create()
        session.add_turn("user", "hello")
        assert len(session.conversation_history) == 1

    def test_add_turn_stores_role_and_content(self) -> None:
        session = Session.create()
        session.add_turn("user", "what is the capital of France?")
        entry = session.conversation_history[0]
        assert entry["role"] == "user"
        assert entry["content"] == "what is the capital of France?"

    def test_add_turn_multiple_turns_in_order(self) -> None:
        session = Session.create()
        session.add_turn("user", "first")
        session.add_turn("assistant", "second")
        session.add_turn("user", "third")
        assert session.conversation_history[0]["content"] == "first"
        assert session.conversation_history[1]["content"] == "second"
        assert session.conversation_history[2]["content"] == "third"

    def test_add_turn_updates_last_active(self) -> None:
        session = Session.create()
        old_last_active = session.last_active
        # Small wait to ensure timestamp changes
        import time

        time.sleep(0.01)
        session.add_turn("user", "something")
        assert session.last_active >= old_last_active

    def test_add_turn_rejects_invalid_role(self) -> None:
        session = Session.create()
        with pytest.raises(ValueError, match="Invalid role"):
            session.add_turn("system", "not allowed")

    def test_add_turn_rejects_empty_role(self) -> None:
        session = Session.create()
        with pytest.raises(ValueError, match="Invalid role"):
            session.add_turn("", "content")

    def test_add_turn_rejects_arbitrary_role(self) -> None:
        session = Session.create()
        with pytest.raises(ValueError, match="Invalid role"):
            session.add_turn("admin", "privileged")

    def test_add_turn_accepts_user_role(self) -> None:
        session = Session.create()
        session.add_turn("user", "hello")
        assert session.conversation_history[-1]["role"] == "user"

    def test_add_turn_accepts_assistant_role(self) -> None:
        session = Session.create()
        session.add_turn("assistant", "hi there")
        assert session.conversation_history[-1]["role"] == "assistant"

    def test_add_turn_rejects_when_max_turns_reached(self) -> None:
        session = Session.create()
        for i in range(500):
            session.add_turn("user" if i % 2 == 0 else "assistant", f"turn {i}")
        with pytest.raises(ValueError, match="maximum"):
            session.add_turn("user", "one too many")

    def test_add_turn_rejects_oversized_content(self) -> None:
        session = Session.create()
        with pytest.raises(ValueError, match="maximum length"):
            session.add_turn("user", "x" * 1_000_001)


class TestSessionGetHistory:
    def test_get_history_returns_list(self) -> None:
        session = Session.create()
        result = session.get_history()
        assert isinstance(result, list)

    def test_get_history_empty_when_no_turns(self) -> None:
        session = Session.create()
        assert session.get_history() == []

    def test_get_history_returns_all_turns(self) -> None:
        session = Session.create()
        session.add_turn("user", "msg1")
        session.add_turn("assistant", "msg2")
        history = session.get_history()
        assert len(history) == 2

    def test_get_history_returns_copy(self) -> None:
        """Mutating the returned list must not affect the session's internal history."""
        session = Session.create()
        session.add_turn("user", "original")
        history = session.get_history()
        history.append({"role": "intruder", "content": "injected"})
        assert len(session.conversation_history) == 1

    def test_get_history_content_matches(self) -> None:
        session = Session.create()
        session.add_turn("user", "hello")
        history = session.get_history()
        assert history[0] == {"role": "user", "content": "hello"}


class TestSessionIsExpired:
    def test_fresh_session_not_expired(self) -> None:
        session = Session.create()
        assert session.is_expired(ttl_minutes=30) is False

    def test_fresh_session_not_expired_short_ttl(self) -> None:
        session = Session.create()
        # Even with 1-minute TTL, a brand-new session should not be expired
        assert session.is_expired(ttl_minutes=1) is False

    def test_old_session_is_expired(self) -> None:
        session = Session.create()
        # Backdate last_active by 31 minutes
        session.last_active = datetime.now(UTC) - timedelta(minutes=31)
        assert session.is_expired(ttl_minutes=30) is True

    def test_exactly_at_boundary_is_expired(self) -> None:
        """A session exactly at the TTL boundary is considered expired."""
        session = Session.create()
        session.last_active = datetime.now(UTC) - timedelta(minutes=30, seconds=1)
        assert session.is_expired(ttl_minutes=30) is True

    def test_just_before_boundary_not_expired(self) -> None:
        session = Session.create()
        session.last_active = datetime.now(UTC) - timedelta(minutes=29)
        assert session.is_expired(ttl_minutes=30) is False

    def test_custom_ttl_respected(self) -> None:
        session = Session.create()
        session.last_active = datetime.now(UTC) - timedelta(minutes=6)
        assert session.is_expired(ttl_minutes=5) is True
        assert session.is_expired(ttl_minutes=10) is False

    def test_add_turn_resets_expiry(self) -> None:
        session = Session.create()
        # Age the session
        session.last_active = datetime.now(UTC) - timedelta(minutes=31)
        assert session.is_expired(ttl_minutes=30) is True
        # Adding a turn refreshes last_active
        session.add_turn("user", "ping")
        assert session.is_expired(ttl_minutes=30) is False


# ---------------------------------------------------------------------------
# SessionManager
# ---------------------------------------------------------------------------


class TestSessionManagerCreate:
    def test_create_session_returns_session(self) -> None:
        manager = SessionManager()
        session = manager.create_session()
        assert isinstance(session, Session)

    def test_create_session_stores_in_manager(self) -> None:
        manager = SessionManager()
        session = manager.create_session()
        assert manager.get_session(session.id) is session

    def test_create_multiple_sessions(self) -> None:
        manager = SessionManager()
        s1 = manager.create_session()
        s2 = manager.create_session()
        assert s1.id != s2.id
        assert len(manager.list_sessions()) == 2


class TestSessionManagerGet:
    def test_get_existing_session(self) -> None:
        manager = SessionManager()
        session = manager.create_session()
        retrieved = manager.get_session(session.id)
        assert retrieved is session

    def test_get_nonexistent_returns_none(self) -> None:
        manager = SessionManager()
        result = manager.get_session("brain-doesnotexist")
        assert result is None

    def test_get_wrong_id_returns_none(self) -> None:
        manager = SessionManager()
        manager.create_session()
        result = manager.get_session("brain-wrongwrong")
        assert result is None


class TestSessionManagerList:
    def test_list_empty_manager(self) -> None:
        manager = SessionManager()
        assert manager.list_sessions() == []

    def test_list_returns_all_sessions(self) -> None:
        manager = SessionManager()
        s1 = manager.create_session()
        s2 = manager.create_session()
        s3 = manager.create_session()
        sessions = manager.list_sessions()
        assert len(sessions) == 3
        ids = {s.id for s in sessions}
        assert s1.id in ids
        assert s2.id in ids
        assert s3.id in ids

    def test_list_returns_copy(self) -> None:
        """Mutating the returned list must not affect internal state."""
        manager = SessionManager()
        manager.create_session()
        listing = manager.list_sessions()
        listing.clear()
        assert len(manager.list_sessions()) == 1


class TestSessionManagerCleanup:
    def test_cleanup_removes_expired_sessions(self) -> None:
        manager = SessionManager()
        old_session = manager.create_session()
        old_session.last_active = datetime.now(UTC) - timedelta(minutes=31)
        _fresh_session = manager.create_session()

        removed = manager.cleanup_expired(ttl_minutes=30)

        assert removed == 1
        assert manager.get_session(old_session.id) is None

    def test_cleanup_keeps_fresh_sessions(self) -> None:
        manager = SessionManager()
        fresh = manager.create_session()

        removed = manager.cleanup_expired(ttl_minutes=30)

        assert removed == 0
        assert manager.get_session(fresh.id) is fresh

    def test_cleanup_returns_count_removed(self) -> None:
        manager = SessionManager()
        for _ in range(3):
            s = manager.create_session()
            s.last_active = datetime.now(UTC) - timedelta(minutes=60)
        manager.create_session()  # one fresh

        removed = manager.cleanup_expired(ttl_minutes=30)
        assert removed == 3

    def test_cleanup_all_expired(self) -> None:
        manager = SessionManager()
        for _ in range(5):
            s = manager.create_session()
            s.last_active = datetime.now(UTC) - timedelta(hours=2)

        removed = manager.cleanup_expired(ttl_minutes=30)
        assert removed == 5
        assert manager.list_sessions() == []

    def test_cleanup_none_expired(self) -> None:
        manager = SessionManager()
        manager.create_session()
        manager.create_session()

        removed = manager.cleanup_expired(ttl_minutes=30)
        assert removed == 0
        assert len(manager.list_sessions()) == 2

    def test_cleanup_custom_ttl(self) -> None:
        manager = SessionManager()
        slightly_old = manager.create_session()
        slightly_old.last_active = datetime.now(UTC) - timedelta(minutes=6)

        # With ttl=5, it should be expired
        removed = manager.cleanup_expired(ttl_minutes=5)
        assert removed == 1

    def test_cleanup_idempotent(self) -> None:
        manager = SessionManager()
        old = manager.create_session()
        old.last_active = datetime.now(UTC) - timedelta(minutes=60)

        first = manager.cleanup_expired(ttl_minutes=30)
        second = manager.cleanup_expired(ttl_minutes=30)
        assert first == 1
        assert second == 0
