"""Observation persistence store for meta-learning.

Stores observations from the cognitive cycle's _observe() phase,
enabling prediction error tracking and meta-cognitive improvement.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path

import aiosqlite
import structlog

from claudedev.brain.models import Observation

logger: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)


class ObservationStore:
    """Async SQLite store for Observation records.

    Each observation records the result of a single _observe() phase:
    prediction error computation and steering directive awareness.

    Args:
        db_path: Path to the SQLite database file. ``~`` is expanded.
    """

    def __init__(self, db_path: str) -> None:
        self._db_path = Path(db_path).expanduser()
        self._conn: aiosqlite.Connection | None = None
        self._db_lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def initialize(self) -> None:
        """Create parent directories, open the DB, enable WAL mode, and create schema."""
        async with self._db_lock:
            if self._conn is not None:
                msg = "ObservationStore is already initialised"
                raise RuntimeError(msg)
            self._db_path.parent.mkdir(parents=True, exist_ok=True)
            self._conn = await aiosqlite.connect(str(self._db_path))
            try:
                await self._conn.execute("PRAGMA journal_mode=WAL")
                await self._conn.execute("PRAGMA busy_timeout=5000")
                await self._conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS observations (
                        id TEXT PRIMARY KEY,
                        task_id TEXT NOT NULL,
                        episode_id TEXT,
                        predicted_outcome TEXT NOT NULL,
                        actual_outcome TEXT NOT NULL,
                        prediction_error REAL NOT NULL,
                        predicted_confidence REAL NOT NULL,
                        actual_confidence REAL NOT NULL,
                        error_category TEXT NOT NULL,
                        has_steering INTEGER NOT NULL DEFAULT 0,
                        directive_type TEXT,
                        directive_message TEXT,
                        timestamp TEXT NOT NULL
                    )
                    """
                )
                await self._conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_observations_task_id ON observations(task_id)"
                )
                await self._conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_observations_prediction_error "
                    "ON observations(prediction_error DESC)"
                )
                await self._conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_observations_timestamp "
                    "ON observations(timestamp DESC)"
                )
                await self._conn.commit()
            except Exception:
                await self._conn.close()
                self._conn = None
                raise
        logger.info("observation_store.initialized", path=str(self._db_path))

    async def close(self) -> None:
        """Close the database connection."""
        async with self._db_lock:
            if self._conn is not None:
                await self._conn.close()
                self._conn = None
                logger.info("observation_store.closed")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _ensure_db(self) -> aiosqlite.Connection:
        """Return the active connection or raise if not initialised."""
        if self._conn is None:
            msg = "ObservationStore is not initialised — call initialize() first"
            raise RuntimeError(msg)
        return self._conn

    @staticmethod
    def _row_to_observation(row_dict: dict[str, object]) -> Observation:
        """Reconstruct an Observation model from a database row dict."""

        timestamp_raw = row_dict["timestamp"]
        if isinstance(timestamp_raw, str):
            ts = datetime.fromisoformat(timestamp_raw)
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=UTC)
        else:
            ts = datetime.now(UTC)

        return Observation(
            id=str(row_dict["id"]),
            task_id=str(row_dict["task_id"]),
            episode_id=str(row_dict["episode_id"]) if row_dict.get("episode_id") else None,
            predicted_outcome=str(row_dict["predicted_outcome"]),
            actual_outcome=str(row_dict["actual_outcome"]),
            prediction_error=float(row_dict["prediction_error"]),  # type: ignore[arg-type]
            predicted_confidence=float(row_dict["predicted_confidence"]),  # type: ignore[arg-type]
            actual_confidence=float(row_dict["actual_confidence"]),  # type: ignore[arg-type]
            error_category=str(row_dict["error_category"]),
            has_steering=bool(row_dict["has_steering"]),
            directive_type=str(row_dict["directive_type"])
            if row_dict.get("directive_type")
            else None,
            directive_message=str(row_dict["directive_message"])
            if row_dict.get("directive_message")
            else None,
            timestamp=ts,
        )

    # ------------------------------------------------------------------
    # Write operations
    # ------------------------------------------------------------------

    async def store(self, observation: Observation) -> str:
        """Persist *observation* and return its id.

        Args:
            observation: The observation to store.

        Returns:
            The observation's id string.
        """
        async with self._db_lock:
            conn = self._ensure_db()
            await conn.execute(
                """
                INSERT INTO observations
                    (id, task_id, episode_id, predicted_outcome, actual_outcome,
                     prediction_error, predicted_confidence, actual_confidence,
                     error_category, has_steering, directive_type, directive_message,
                     timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    observation.id,
                    observation.task_id,
                    observation.episode_id,
                    observation.predicted_outcome,
                    observation.actual_outcome,
                    observation.prediction_error,
                    observation.predicted_confidence,
                    observation.actual_confidence,
                    observation.error_category,
                    int(observation.has_steering),
                    observation.directive_type,
                    observation.directive_message,
                    observation.timestamp.isoformat(),
                ),
            )
            await conn.commit()
        logger.debug(
            "observation_store.stored",
            observation_id=observation.id,
            task_id=observation.task_id,
            prediction_error=observation.prediction_error,
        )
        return observation.id

    # ------------------------------------------------------------------
    # Read operations
    # ------------------------------------------------------------------

    async def get_recent(self, limit: int = 20) -> list[Observation]:
        """Return recent observations for meta-learning analysis.

        Args:
            limit: Maximum number of observations to return.

        Returns:
            List of Observation models, ordered by timestamp descending.
        """
        async with self._db_lock:
            conn = self._ensure_db()
            async with conn.execute(
                "SELECT * FROM observations ORDER BY timestamp DESC LIMIT ?",
                (limit,),
            ) as cursor:
                rows = await cursor.fetchall()
                columns = [desc[0] for desc in cursor.description]
        return [self._row_to_observation(dict(zip(columns, row, strict=True))) for row in rows]

    async def get_high_error_observations(
        self, threshold: float = 0.5, limit: int = 10
    ) -> list[Observation]:
        """Return observations with prediction error at or above *threshold*.

        Args:
            threshold: Minimum prediction_error value (inclusive).
            limit: Maximum number of observations to return.

        Returns:
            List of Observation models, ordered by prediction_error descending.
        """
        async with self._db_lock:
            conn = self._ensure_db()
            async with conn.execute(
                "SELECT * FROM observations "
                "WHERE prediction_error >= ? "
                "ORDER BY prediction_error DESC LIMIT ?",
                (threshold, limit),
            ) as cursor:
                rows = await cursor.fetchall()
                columns = [desc[0] for desc in cursor.description]
        return [self._row_to_observation(dict(zip(columns, row, strict=True))) for row in rows]

    async def get_prediction_error_stats(self) -> dict[str, float]:
        """Compute aggregate prediction error statistics.

        Returns:
            Dict with keys ``count``, ``avg_error``, ``max_error``, ``min_error``.
            All values are floats; returns zeros when the store is empty.
        """
        async with self._db_lock:
            conn = self._ensure_db()
            async with conn.execute(
                "SELECT COUNT(*), AVG(prediction_error), "
                "MAX(prediction_error), MIN(prediction_error) "
                "FROM observations"
            ) as cursor:
                row = await cursor.fetchone()
        if row is None or row[0] == 0:
            return {"count": 0.0, "avg_error": 0.0, "max_error": 0.0, "min_error": 0.0}
        return {
            "count": float(row[0]),
            "avg_error": float(row[1]),
            "max_error": float(row[2]),
            "min_error": float(row[3]),
        }

    async def count(self) -> int:
        """Return the total number of stored observations.

        Returns:
            Integer count of all observations.
        """
        async with self._db_lock:
            conn = self._ensure_db()
            async with conn.execute("SELECT COUNT(*) FROM observations") as cursor:
                row = await cursor.fetchone()
        return int(row[0])  # type: ignore[index]
