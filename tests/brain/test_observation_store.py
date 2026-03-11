"""Tests for ObservationStore — async SQLite store for cognitive-cycle observations."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path

from claudedev.brain.memory.observation_store import ObservationStore
from claudedev.brain.models import Observation

# ---------------------------------------------------------------------------
# Fixtures and helpers
# ---------------------------------------------------------------------------


@pytest.fixture
async def store(tmp_path: Path) -> ObservationStore:  # type: ignore[misc]
    """Yield an initialised ObservationStore backed by a temporary SQLite file."""
    s = ObservationStore(str(tmp_path / "test_observations.db"))
    await s.initialize()
    yield s
    await s.close()


def _make_observation(**kwargs: object) -> Observation:
    """Return an Observation with sensible defaults, overrideable via kwargs."""
    defaults: dict[str, object] = {
        "task_id": "task-abc123",
        "predicted_outcome": "success (confidence=0.85)",
        "actual_outcome": "success",
        "prediction_error": 0.0,
        "predicted_confidence": 0.85,
        "actual_confidence": 0.9,
        "error_category": "confidence_gap",
        "has_steering": False,
        "directive_type": None,
        "directive_message": None,
    }
    defaults.update(kwargs)
    return Observation(**defaults)


# ---------------------------------------------------------------------------
# TestInitialize
# ---------------------------------------------------------------------------


class TestInitialize:
    async def test_initialize_creates_db(self, tmp_path: Path) -> None:
        db_path = str(tmp_path / "init_test.db")
        s = ObservationStore(db_path)
        await s.initialize()
        assert (tmp_path / "init_test.db").exists()
        await s.close()

    async def test_initialize_creates_parent_dirs(self, tmp_path: Path) -> None:
        db_path = str(tmp_path / "nested" / "deep" / "observations.db")
        s = ObservationStore(db_path)
        await s.initialize()
        assert (tmp_path / "nested" / "deep" / "observations.db").exists()
        await s.close()

    async def test_double_initialize_raises(self, tmp_path: Path) -> None:
        db_path = str(tmp_path / "double_init.db")
        s = ObservationStore(db_path)
        await s.initialize()
        with pytest.raises(RuntimeError, match="already initialised"):
            await s.initialize()
        await s.close()

    async def test_initialize_rollback_on_failure(self, tmp_path: Path) -> None:
        from unittest.mock import AsyncMock, patch

        db_path = str(tmp_path / "rollback.db")
        s = ObservationStore(db_path)

        mock_conn = AsyncMock()
        mock_conn.execute.side_effect = RuntimeError("schema creation failed")
        mock_conn.close = AsyncMock()

        async def fake_connect(*_args: object, **_kwargs: object) -> AsyncMock:
            return mock_conn

        with (
            patch("aiosqlite.connect", side_effect=fake_connect),
            pytest.raises(RuntimeError, match="schema creation failed"),
        ):
            await s.initialize()

        mock_conn.close.assert_awaited_once()
        assert s._conn is None


# ---------------------------------------------------------------------------
# TestStoreAndRetrieve
# ---------------------------------------------------------------------------


class TestStoreAndRetrieve:
    async def test_store_and_get_recent(self, store: ObservationStore) -> None:
        obs = _make_observation()
        returned_id = await store.store(obs)
        assert returned_id == obs.id

        results = await store.get_recent(limit=1)
        assert len(results) == 1
        assert results[0]["id"] == obs.id
        assert results[0]["task_id"] == obs.task_id

    async def test_store_preserves_all_fields(self, store: ObservationStore) -> None:
        obs = _make_observation(
            task_id="task-xyz",
            predicted_outcome="success (confidence=0.90)",
            actual_outcome="success",
            prediction_error=0.05,
            predicted_confidence=0.90,
            actual_confidence=0.85,
            error_category="confidence_gap",
        )
        await store.store(obs)
        results = await store.get_recent(limit=1)
        assert len(results) == 1
        row = results[0]
        assert row["task_id"] == "task-xyz"
        assert row["prediction_error"] == pytest.approx(0.05)
        assert row["predicted_confidence"] == pytest.approx(0.90)
        assert row["actual_confidence"] == pytest.approx(0.85)
        assert row["error_category"] == "confidence_gap"

    async def test_store_with_steering(self, store: ObservationStore) -> None:
        obs = _make_observation(
            has_steering=True,
            directive_type="pivot",
            directive_message="Use Redis instead",
        )
        await store.store(obs)
        results = await store.get_recent(limit=1)
        row = results[0]
        assert row["has_steering"] == 1
        assert row["directive_type"] == "pivot"
        assert row["directive_message"] == "Use Redis instead"

    async def test_store_without_steering(self, store: ObservationStore) -> None:
        obs = _make_observation(has_steering=False, directive_type=None, directive_message=None)
        await store.store(obs)
        results = await store.get_recent(limit=1)
        row = results[0]
        assert row["has_steering"] == 0
        assert row["directive_type"] is None
        assert row["directive_message"] is None

    async def test_get_recent_ordering(self, store: ObservationStore) -> None:
        old_obs = _make_observation(task_id="old-task")
        new_obs = _make_observation(task_id="new-task")

        await store.store(old_obs)
        await store.store(new_obs)

        results = await store.get_recent(limit=10)
        assert len(results) == 2
        # Most recently stored appears first (DESC timestamp ordering)
        assert results[0]["task_id"] == "new-task"
        assert results[1]["task_id"] == "old-task"

    async def test_get_recent_limit_respected(self, store: ObservationStore) -> None:
        for i in range(10):
            await store.store(_make_observation(task_id=f"task-{i}"))
        results = await store.get_recent(limit=5)
        assert len(results) == 5

    async def test_get_recent_empty_store(self, store: ObservationStore) -> None:
        results = await store.get_recent()
        assert results == []


# ---------------------------------------------------------------------------
# TestHighErrorObservations
# ---------------------------------------------------------------------------


class TestHighErrorObservations:
    async def test_filters_by_threshold(self, store: ObservationStore) -> None:
        low_error = _make_observation(prediction_error=0.2, error_category="confidence_gap")
        high_error = _make_observation(prediction_error=0.8, error_category="success_mismatch")
        await store.store(low_error)
        await store.store(high_error)

        results = await store.get_high_error_observations(threshold=0.5)
        assert len(results) == 1
        assert results[0]["prediction_error"] == pytest.approx(0.8)

    async def test_includes_threshold_boundary(self, store: ObservationStore) -> None:
        obs = _make_observation(prediction_error=0.5, error_category="outcome_divergence")
        await store.store(obs)
        results = await store.get_high_error_observations(threshold=0.5)
        assert len(results) == 1

    async def test_ordered_by_error_descending(self, store: ObservationStore) -> None:
        obs_a = _make_observation(prediction_error=0.6, error_category="success_mismatch")
        obs_b = _make_observation(prediction_error=0.9, error_category="success_mismatch")
        obs_c = _make_observation(prediction_error=0.7, error_category="outcome_divergence")
        await store.store(obs_a)
        await store.store(obs_b)
        await store.store(obs_c)

        results = await store.get_high_error_observations(threshold=0.5)
        assert len(results) == 3
        errors = [r["prediction_error"] for r in results]
        assert errors == sorted(errors, reverse=True)

    async def test_limit_respected(self, store: ObservationStore) -> None:
        for _ in range(10):
            await store.store(
                _make_observation(prediction_error=1.0, error_category="success_mismatch")
            )
        results = await store.get_high_error_observations(threshold=0.5, limit=3)
        assert len(results) == 3

    async def test_empty_result_when_all_below_threshold(self, store: ObservationStore) -> None:
        await store.store(_make_observation(prediction_error=0.1, error_category="confidence_gap"))
        results = await store.get_high_error_observations(threshold=0.5)
        assert results == []


# ---------------------------------------------------------------------------
# TestPredictionErrorStats
# ---------------------------------------------------------------------------


class TestPredictionErrorStats:
    async def test_empty_store_returns_zeros(self, store: ObservationStore) -> None:
        stats = await store.get_prediction_error_stats()
        assert stats == {"count": 0.0, "avg_error": 0.0, "max_error": 0.0, "min_error": 0.0}

    async def test_single_observation(self, store: ObservationStore) -> None:
        obs = _make_observation(prediction_error=0.6, error_category="success_mismatch")
        await store.store(obs)
        stats = await store.get_prediction_error_stats()
        assert stats["count"] == 1.0
        assert stats["avg_error"] == pytest.approx(0.6)
        assert stats["max_error"] == pytest.approx(0.6)
        assert stats["min_error"] == pytest.approx(0.6)

    async def test_multiple_observations(self, store: ObservationStore) -> None:
        await store.store(_make_observation(prediction_error=0.2, error_category="confidence_gap"))
        await store.store(
            _make_observation(prediction_error=0.8, error_category="success_mismatch")
        )
        await store.store(
            _make_observation(prediction_error=0.5, error_category="outcome_divergence")
        )

        stats = await store.get_prediction_error_stats()
        assert stats["count"] == 3.0
        assert stats["avg_error"] == pytest.approx(0.5)
        assert stats["max_error"] == pytest.approx(0.8)
        assert stats["min_error"] == pytest.approx(0.2)


# ---------------------------------------------------------------------------
# TestCount
# ---------------------------------------------------------------------------


class TestCount:
    async def test_empty_store(self, store: ObservationStore) -> None:
        assert await store.count() == 0

    async def test_count_increments(self, store: ObservationStore) -> None:
        await store.store(_make_observation())
        assert await store.count() == 1
        await store.store(_make_observation())
        assert await store.count() == 2


# ---------------------------------------------------------------------------
# TestLifecycle
# ---------------------------------------------------------------------------


class TestLifecycle:
    async def test_not_initialized_raises_on_store(self, tmp_path: Path) -> None:
        s = ObservationStore(str(tmp_path / "uninit.db"))
        obs = _make_observation()
        with pytest.raises(RuntimeError, match="not initialised"):
            await s.store(obs)

    async def test_not_initialized_raises_on_get_recent(self, tmp_path: Path) -> None:
        s = ObservationStore(str(tmp_path / "uninit2.db"))
        with pytest.raises(RuntimeError, match="not initialised"):
            await s.get_recent()

    async def test_not_initialized_raises_on_stats(self, tmp_path: Path) -> None:
        s = ObservationStore(str(tmp_path / "uninit3.db"))
        with pytest.raises(RuntimeError, match="not initialised"):
            await s.get_prediction_error_stats()

    async def test_close_and_reopen(self, tmp_path: Path) -> None:
        db_path = str(tmp_path / "reopen.db")
        s = ObservationStore(db_path)
        await s.initialize()
        obs = _make_observation(task_id="persistent-task")
        await s.store(obs)
        await s.close()

        # Reopen and verify data persisted
        s2 = ObservationStore(db_path)
        await s2.initialize()
        results = await s2.get_recent(limit=1)
        assert len(results) == 1
        assert results[0]["task_id"] == "persistent-task"
        await s2.close()

    async def test_close_idempotent(self, store: ObservationStore) -> None:
        """Closing an already-closed store should not raise."""
        await store.close()
        await store.close()  # second close is a no-op


# ---------------------------------------------------------------------------
# TestConcurrency
# ---------------------------------------------------------------------------


class TestConcurrency:
    async def test_concurrent_writes(self, store: ObservationStore) -> None:
        observations = [_make_observation(task_id=f"task-{i}") for i in range(20)]
        await asyncio.gather(*(store.store(obs) for obs in observations))
        assert await store.count() == 20


# ---------------------------------------------------------------------------
# TestEdgeCases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    async def test_error_category_success_mismatch(self, store: ObservationStore) -> None:
        obs = _make_observation(
            prediction_error=1.0,
            error_category="success_mismatch",
            actual_outcome="failed: timeout",
        )
        await store.store(obs)
        results = await store.get_recent(limit=1)
        assert results[0]["error_category"] == "success_mismatch"

    async def test_error_category_outcome_divergence(self, store: ObservationStore) -> None:
        obs = _make_observation(
            prediction_error=0.4,
            error_category="outcome_divergence",
        )
        await store.store(obs)
        results = await store.get_recent(limit=1)
        assert results[0]["error_category"] == "outcome_divergence"

    async def test_episode_id_nullable(self, store: ObservationStore) -> None:
        obs = Observation(
            task_id="task-no-episode",
            episode_id=None,
            predicted_outcome="unknown (no prior episodes)",
            actual_outcome="success",
            prediction_error=0.0,
            predicted_confidence=0.5,
            actual_confidence=0.8,
            error_category="unknown",
        )
        await store.store(obs)
        results = await store.get_recent(limit=1)
        assert results[0]["episode_id"] is None

    async def test_zero_prediction_error(self, store: ObservationStore) -> None:
        obs = _make_observation(prediction_error=0.0, error_category="confidence_gap")
        await store.store(obs)
        stats = await store.get_prediction_error_stats()
        assert stats["avg_error"] == pytest.approx(0.0)
        assert stats["min_error"] == pytest.approx(0.0)

    async def test_max_prediction_error(self, store: ObservationStore) -> None:
        obs = _make_observation(prediction_error=1.0, error_category="success_mismatch")
        await store.store(obs)
        stats = await store.get_prediction_error_stats()
        assert stats["max_error"] == pytest.approx(1.0)
