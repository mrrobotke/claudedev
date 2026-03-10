"""Episodic memory store for the NEXUS brain.

Async SQLite store for autobiographical task memories using aiosqlite.
Each episode captures one task attempt: the approach taken, outcome,
tools used, files touched, and any error messages encountered.
"""

from __future__ import annotations

import json
from pathlib import Path

import aiosqlite
import structlog
from aiosqlite import Row

from claudedev.brain.models import EpisodicMemory

logger: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)

_CREATE_SCHEMA = """
CREATE TABLE IF NOT EXISTS episodes (
    id TEXT PRIMARY KEY,
    task TEXT NOT NULL,
    approach TEXT NOT NULL,
    outcome TEXT NOT NULL,
    tools_used TEXT NOT NULL DEFAULT '[]',
    files_modified TEXT NOT NULL DEFAULT '[]',
    error_messages TEXT NOT NULL DEFAULT '[]',
    confidence REAL NOT NULL DEFAULT 0.5,
    timestamp TEXT NOT NULL,
    consolidated INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_episodes_timestamp ON episodes(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_episodes_consolidated ON episodes(consolidated);
"""


class EpisodicStore:
    """Async SQLite store for autobiographical task memories.

    Each episode records a single task attempt: how it was approached,
    what happened, which tools and files were involved, and how confident
    the brain is in the recorded outcome.

    Args:
        db_path: Path to the SQLite database file. ``~`` is expanded.
    """

    def __init__(self, db_path: str) -> None:
        self._db_path = Path(db_path).expanduser()
        self._conn: aiosqlite.Connection | None = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def initialize(self) -> None:
        """Create parent directories, open the DB, enable WAL mode, and create schema."""
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = await aiosqlite.connect(str(self._db_path))
        await self._conn.execute("PRAGMA journal_mode=WAL")
        await self._conn.execute("PRAGMA busy_timeout=5000")
        await self._conn.executescript(_CREATE_SCHEMA)
        await self._conn.commit()
        logger.info("episodic_store.initialized", path=str(self._db_path))

    async def close(self) -> None:
        """Close the database connection."""
        if self._conn is not None:
            await self._conn.close()
            self._conn = None
            logger.info("episodic_store.closed")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _ensure_db(self) -> aiosqlite.Connection:
        """Return the active connection or raise if not initialised."""
        if self._conn is None:
            msg = "EpisodicStore is not initialised — call initialize() first"
            raise RuntimeError(msg)
        return self._conn

    @staticmethod
    def _row_to_episode(row: Row) -> EpisodicMemory:
        """Convert a DB row tuple to an EpisodicMemory model."""
        (
            id_,
            task,
            approach,
            outcome,
            tools_used_raw,
            files_modified_raw,
            error_messages_raw,
            confidence,
            timestamp_raw,
            consolidated_raw,
        ) = row
        return EpisodicMemory.model_validate(
            {
                "id": id_,
                "task": task,
                "approach": approach,
                "outcome": outcome,
                "tools_used": json.loads(tools_used_raw),
                "files_modified": json.loads(files_modified_raw),
                "error_messages": json.loads(error_messages_raw),
                "confidence": confidence,
                "timestamp": timestamp_raw,
                "consolidated": bool(consolidated_raw),
            }
        )

    # ------------------------------------------------------------------
    # Write operations
    # ------------------------------------------------------------------

    async def store(self, episode: EpisodicMemory) -> str:
        """Persist *episode* and return its id.

        Args:
            episode: The episodic memory to store.

        Returns:
            The episode's id string.
        """
        conn = self._ensure_db()
        await conn.execute(
            """
            INSERT INTO episodes
                (id, task, approach, outcome, tools_used, files_modified,
                 error_messages, confidence, timestamp, consolidated)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                episode.id,
                episode.task,
                episode.approach,
                episode.outcome,
                json.dumps(episode.tools_used),
                json.dumps(episode.files_modified),
                json.dumps(episode.error_messages),
                episode.confidence,
                episode.timestamp.isoformat(),
                int(episode.consolidated),
            ),
        )
        await conn.commit()
        logger.debug("episodic_store.stored", episode_id=episode.id)
        return episode.id

    async def update(self, episode: EpisodicMemory) -> None:
        """Replace the stored episode with the same id.

        Args:
            episode: Updated episodic memory (matched by id).
        """
        conn = self._ensure_db()
        await conn.execute(
            """
            UPDATE episodes
            SET task = ?,
                approach = ?,
                outcome = ?,
                tools_used = ?,
                files_modified = ?,
                error_messages = ?,
                confidence = ?,
                timestamp = ?,
                consolidated = ?
            WHERE id = ?
            """,
            (
                episode.task,
                episode.approach,
                episode.outcome,
                json.dumps(episode.tools_used),
                json.dumps(episode.files_modified),
                json.dumps(episode.error_messages),
                episode.confidence,
                episode.timestamp.isoformat(),
                int(episode.consolidated),
                episode.id,
            ),
        )
        await conn.commit()
        logger.debug("episodic_store.updated", episode_id=episode.id)

    # ------------------------------------------------------------------
    # Read operations
    # ------------------------------------------------------------------

    async def get_by_id(self, episode_id: str) -> EpisodicMemory | None:
        """Fetch a single episode by id.

        Args:
            episode_id: The episode's primary key.

        Returns:
            The matching EpisodicMemory or None if not found.
        """
        conn = self._ensure_db()
        async with conn.execute(
            "SELECT id, task, approach, outcome, tools_used, files_modified, "
            "error_messages, confidence, timestamp, consolidated "
            "FROM episodes WHERE id = ?",
            (episode_id,),
        ) as cursor:
            row = await cursor.fetchone()
        if row is None:
            return None
        return self._row_to_episode(row)

    async def search(self, query: str, limit: int = 20) -> list[EpisodicMemory]:
        """Search episodes by keyword across task, approach, and outcome fields.

        The search is case-insensitive and uses LIKE pattern matching.

        Args:
            query: Search term (partial match).
            limit: Maximum number of results to return.

        Returns:
            List of matching episodes ordered by timestamp descending.
        """
        conn = self._ensure_db()
        pattern = f"%{query}%"
        async with conn.execute(
            """
            SELECT id, task, approach, outcome, tools_used, files_modified,
                   error_messages, confidence, timestamp, consolidated
            FROM episodes
            WHERE task LIKE ? COLLATE NOCASE
               OR approach LIKE ? COLLATE NOCASE
               OR outcome LIKE ? COLLATE NOCASE
            ORDER BY timestamp DESC
            LIMIT ?
            """,
            (pattern, pattern, pattern, limit),
        ) as cursor:
            rows = await cursor.fetchall()
        return [self._row_to_episode(r) for r in rows]

    async def get_recent(self, limit: int = 10) -> list[EpisodicMemory]:
        """Return the most recent episodes.

        Args:
            limit: Maximum number of episodes to return.

        Returns:
            List of episodes ordered by timestamp descending.
        """
        conn = self._ensure_db()
        async with conn.execute(
            """
            SELECT id, task, approach, outcome, tools_used, files_modified,
                   error_messages, confidence, timestamp, consolidated
            FROM episodes
            ORDER BY timestamp DESC
            LIMIT ?
            """,
            (limit,),
        ) as cursor:
            rows = await cursor.fetchall()
        return [self._row_to_episode(r) for r in rows]

    async def get_unconsolidated(self, limit: int = 100) -> list[EpisodicMemory]:
        """Return episodes that have not yet been consolidated.

        Args:
            limit: Maximum number of episodes to return.

        Returns:
            List of unconsolidated episodes.
        """
        conn = self._ensure_db()
        async with conn.execute(
            """
            SELECT id, task, approach, outcome, tools_used, files_modified,
                   error_messages, confidence, timestamp, consolidated
            FROM episodes
            WHERE consolidated = 0
            LIMIT ?
            """,
            (limit,),
        ) as cursor:
            rows = await cursor.fetchall()
        return [self._row_to_episode(r) for r in rows]

    async def count(self) -> int:
        """Return the total number of stored episodes.

        Returns:
            Integer count of all episodes.
        """
        conn = self._ensure_db()
        async with conn.execute("SELECT COUNT(*) FROM episodes") as cursor:
            row = await cursor.fetchone()
        # row is always non-None for COUNT(*)
        return int(row[0])  # type: ignore[index]
