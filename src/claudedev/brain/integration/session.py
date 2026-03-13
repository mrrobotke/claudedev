"""Brain session management — tracks conversation history across turns.

Sessions are in-memory only and expire after a configurable TTL.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import structlog

logger = structlog.get_logger(__name__)


class Session:
    """A single conversation session with history tracking.

    Maintains an ordered list of (role, content) turns and timestamps
    for activity tracking and TTL-based expiry.
    """

    def __init__(self, session_id: str) -> None:
        self.id: str = session_id
        self.conversation_history: list[dict[str, str]] = []
        self.created_at: datetime = datetime.now(UTC)
        self.last_active: datetime = datetime.now(UTC)
        self._max_turns: int = 500

    @classmethod
    def create(cls) -> Session:
        """Create a new session with a generated ID.

        Returns:
            A fresh Session instance with a unique ``brain-<hex>`` identifier.
        """
        session_id = f"brain-{uuid.uuid4().hex[:12]}"
        session = cls(session_id)
        logger.debug("session_created", session_id=session_id)
        return session

    _VALID_ROLES: frozenset[str] = frozenset({"user", "assistant"})

    def add_turn(self, role: str, content: str) -> None:
        """Append a conversation turn and update the last-active timestamp.

        Args:
            role: The speaker role — must be ``"user"`` or ``"assistant"``.
            content: The message text for this turn.

        Raises:
            ValueError: If *role* is not one of the valid roles.
            ValueError: If the session has reached the maximum number of turns.
            ValueError: If *content* exceeds the maximum allowed length.
        """
        if role not in self._VALID_ROLES:
            msg = f"Invalid role {role!r} — must be one of {sorted(self._VALID_ROLES)}"
            raise ValueError(msg)
        if len(self.conversation_history) >= self._max_turns:
            msg = f"Session {self.id} has reached the maximum of {self._max_turns} turns"
            raise ValueError(msg)
        if len(content) > 1_000_000:
            msg = "Turn content exceeds maximum length of 1,000,000 characters"
            raise ValueError(msg)
        self.conversation_history.append({"role": role, "content": content})
        self.last_active = datetime.now(UTC)

    def get_history(self) -> list[dict[str, str]]:
        """Return a shallow copy of the conversation history.

        Returns:
            A new list containing all recorded turns in order.
        """
        return list(self.conversation_history)

    def is_expired(self, ttl_minutes: int = 30) -> bool:
        """Check whether this session has exceeded its TTL.

        Args:
            ttl_minutes: Inactivity threshold in minutes. Defaults to 30.

        Returns:
            ``True`` if the session has been inactive longer than *ttl_minutes*.
        """
        cutoff = datetime.now(UTC) - timedelta(minutes=ttl_minutes)
        return self.last_active < cutoff


class SessionManager:
    """In-memory registry of active brain sessions.

    Provides creation, retrieval, listing, and TTL-based cleanup of
    :class:`Session` instances.
    """

    def __init__(self) -> None:
        self._sessions: dict[str, Session] = {}

    def create_session(self) -> Session:
        """Create a new session and register it.

        Returns:
            The newly created :class:`Session`.
        """
        session = Session.create()
        self._sessions[session.id] = session
        logger.info("session_registered", session_id=session.id)
        return session

    def get_session(self, session_id: str) -> Session | None:
        """Retrieve a session by its ID.

        Args:
            session_id: The identifier returned by :meth:`create_session`.

        Returns:
            The :class:`Session` if found, or ``None``.
        """
        return self._sessions.get(session_id)

    def list_sessions(self) -> list[Session]:
        """Return all currently registered sessions.

        Returns:
            A list of all :class:`Session` instances (order not guaranteed).
        """
        return list(self._sessions.values())

    def cleanup_expired(self, ttl_minutes: int = 30) -> int:
        """Remove sessions that have exceeded the TTL.

        Args:
            ttl_minutes: Inactivity threshold forwarded to :meth:`Session.is_expired`.

        Returns:
            The number of sessions that were removed.
        """
        expired = [
            sid for sid, session in self._sessions.items() if session.is_expired(ttl_minutes)
        ]
        for sid in expired:
            del self._sessions[sid]
        if expired:
            logger.info("sessions_cleaned_up", count=len(expired))
        return len(expired)
