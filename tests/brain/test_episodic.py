"""Tests for EpisodicStore — async SQLite store for autobiographical task memories."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path

from claudedev.brain.memory.episodic import EpisodicStore
from claudedev.brain.models import EpisodicMemory

# ---------------------------------------------------------------------------
# Fixtures and helpers
# ---------------------------------------------------------------------------


@pytest.fixture
async def store(tmp_path: Path) -> EpisodicStore:  # type: ignore[misc]
    """Yield an initialised EpisodicStore backed by a temporary SQLite file."""
    s = EpisodicStore(str(tmp_path / "test.db"))
    await s.initialize()
    yield s
    await s.close()


def _make_episode(**kwargs: object) -> EpisodicMemory:
    """Return an EpisodicMemory with sensible defaults, overrideable via kwargs."""
    defaults: dict[str, object] = {
        "task": "implement login feature",
        "approach": "use JWT tokens",
        "outcome": "success — tests pass",
        "tools_used": ["bash", "edit"],
        "files_modified": ["auth.py", "tests/test_auth.py"],
        "error_messages": [],
        "confidence": 0.9,
        "consolidated": False,
    }
    defaults.update(kwargs)
    return EpisodicMemory(**defaults)


# ---------------------------------------------------------------------------
# TestStoreCRUD
# ---------------------------------------------------------------------------


class TestStoreCRUD:
    async def test_store_and_retrieve(self, store: EpisodicStore) -> None:
        episode = _make_episode()
        returned_id = await store.store(episode)
        assert returned_id == episode.id

        fetched = await store.get_by_id(episode.id)
        assert fetched is not None
        assert fetched.id == episode.id
        assert fetched.task == episode.task
        assert fetched.approach == episode.approach
        assert fetched.outcome == episode.outcome

    async def test_preserves_all_fields(self, store: EpisodicStore) -> None:
        episode = _make_episode(
            tools_used=["bash", "read", "edit"],
            files_modified=["src/foo.py", "src/bar.py"],
            error_messages=["ModuleNotFoundError: no module named 'x'"],
            confidence=0.75,
        )
        await store.store(episode)
        fetched = await store.get_by_id(episode.id)
        assert fetched is not None
        assert fetched.tools_used == ["bash", "read", "edit"]
        assert fetched.files_modified == ["src/foo.py", "src/bar.py"]
        assert fetched.error_messages == ["ModuleNotFoundError: no module named 'x'"]
        assert fetched.confidence == pytest.approx(0.75)
        assert fetched.consolidated is False

    async def test_get_nonexistent_returns_none(self, store: EpisodicStore) -> None:
        result = await store.get_by_id("nonexistent-id-abc123")
        assert result is None

    async def test_update_episode(self, store: EpisodicStore) -> None:
        episode = _make_episode(consolidated=False)
        await store.store(episode)

        episode.consolidated = True
        episode.outcome = "revised outcome"
        await store.update(episode)

        fetched = await store.get_by_id(episode.id)
        assert fetched is not None
        assert fetched.consolidated is True
        assert fetched.outcome == "revised outcome"

    async def test_count_empty(self, store: EpisodicStore) -> None:
        assert await store.count() == 0

    async def test_count_one(self, store: EpisodicStore) -> None:
        await store.store(_make_episode())
        assert await store.count() == 1

    async def test_count_two(self, store: EpisodicStore) -> None:
        await store.store(_make_episode(task="first task"))
        await store.store(_make_episode(task="second task"))
        assert await store.count() == 2


# ---------------------------------------------------------------------------
# TestSearch
# ---------------------------------------------------------------------------


class TestSearch:
    async def test_keyword_in_task(self, store: EpisodicStore) -> None:
        await store.store(_make_episode(task="implement authentication module"))
        await store.store(_make_episode(task="fix database migration"))

        results = await store.search("authentication")
        assert len(results) == 1
        assert results[0].task == "implement authentication module"

    async def test_keyword_in_approach(self, store: EpisodicStore) -> None:
        await store.store(_make_episode(approach="use bcrypt for password hashing"))
        await store.store(_make_episode(approach="use JWT tokens"))

        results = await store.search("bcrypt")
        assert len(results) == 1
        assert "bcrypt" in results[0].approach

    async def test_keyword_in_outcome(self, store: EpisodicStore) -> None:
        await store.store(_make_episode(outcome="all 42 tests passed successfully"))
        await store.store(_make_episode(outcome="failed with import error"))

        results = await store.search("42 tests")
        assert len(results) == 1
        assert "42 tests" in results[0].outcome

    async def test_no_results(self, store: EpisodicStore) -> None:
        await store.store(_make_episode(task="fix login bug"))
        results = await store.search("nonexistent_keyword_xyz")
        assert results == []

    async def test_empty_store(self, store: EpisodicStore) -> None:
        results = await store.search("anything")
        assert results == []

    async def test_limit_respected(self, store: EpisodicStore) -> None:
        for i in range(10):
            await store.store(_make_episode(task=f"implement feature {i}"))
        results = await store.search("implement", limit=5)
        assert len(results) <= 5

    async def test_case_insensitive(self, store: EpisodicStore) -> None:
        await store.store(_make_episode(task="Implement AUTH Module"))
        results_lower = await store.search("auth")
        results_upper = await store.search("AUTH")
        results_mixed = await store.search("Auth")
        assert len(results_lower) == 1
        assert len(results_upper) == 1
        assert len(results_mixed) == 1


# ---------------------------------------------------------------------------
# TestRecency
# ---------------------------------------------------------------------------


class TestRecency:
    async def test_ordering(self, store: EpisodicStore) -> None:
        # Store with explicit older timestamps to guarantee ordering.
        old = _make_episode(task="old task")
        old.timestamp = datetime(2024, 1, 1, tzinfo=UTC)
        new = _make_episode(task="new task")
        new.timestamp = datetime(2025, 6, 1, tzinfo=UTC)

        await store.store(old)
        await store.store(new)

        results = await store.get_recent(limit=10)
        assert len(results) == 2
        assert results[0].task == "new task"
        assert results[1].task == "old task"

    async def test_limit_respected(self, store: EpisodicStore) -> None:
        for i in range(15):
            await store.store(_make_episode(task=f"task {i}"))
        results = await store.get_recent(limit=5)
        assert len(results) == 5

    async def test_empty_store(self, store: EpisodicStore) -> None:
        results = await store.get_recent()
        assert results == []


# ---------------------------------------------------------------------------
# TestConsolidation
# ---------------------------------------------------------------------------


class TestConsolidation:
    async def test_get_unconsolidated_filters_correctly(self, store: EpisodicStore) -> None:
        unconsolidated = _make_episode(task="not yet consolidated", consolidated=False)
        consolidated = _make_episode(task="already consolidated", consolidated=True)
        await store.store(unconsolidated)
        await store.store(consolidated)

        results = await store.get_unconsolidated()
        assert len(results) == 1
        assert results[0].task == "not yet consolidated"

    async def test_unconsolidated_limit_respected(self, store: EpisodicStore) -> None:
        for i in range(10):
            await store.store(_make_episode(task=f"task {i}", consolidated=False))

        results = await store.get_unconsolidated(limit=3)
        assert len(results) == 3

    async def test_all_consolidated_returns_empty(self, store: EpisodicStore) -> None:
        await store.store(_make_episode(consolidated=True))
        results = await store.get_unconsolidated()
        assert results == []


# ---------------------------------------------------------------------------
# TestEdgeCases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    async def test_special_chars_apostrophe_and_quotes(self, store: EpisodicStore) -> None:
        episode = _make_episode(
            task="O'Brien's task with \"quotes\"",
            approach="approach with 'single' and \"double\" quotes",
            outcome="it's done",
        )
        await store.store(episode)
        fetched = await store.get_by_id(episode.id)
        assert fetched is not None
        assert fetched.task == "O'Brien's task with \"quotes\""
        assert "single" in fetched.approach
        assert fetched.outcome == "it's done"

    async def test_unicode_and_emoji(self, store: EpisodicStore) -> None:
        episode = _make_episode(
            task="日本語タスク — Ünïcödé test 🚀",
            approach="アプローチ: use 🎉 strategy",
            outcome="成功 ✅",
        )
        await store.store(episode)
        fetched = await store.get_by_id(episode.id)
        assert fetched is not None
        assert fetched.task == "日本語タスク — Ünïcödé test 🚀"
        assert "🎉" in fetched.approach
        assert fetched.outcome == "成功 ✅"

    async def test_large_content(self, store: EpisodicStore) -> None:
        large_text = "x" * 100_000
        episode = _make_episode(task=large_text)
        await store.store(episode)
        fetched = await store.get_by_id(episode.id)
        assert fetched is not None
        assert len(fetched.task) == 100_000

    async def test_empty_lists_stored_correctly(self, store: EpisodicStore) -> None:
        episode = _make_episode(
            tools_used=[],
            files_modified=[],
            error_messages=[],
        )
        await store.store(episode)
        fetched = await store.get_by_id(episode.id)
        assert fetched is not None
        assert fetched.tools_used == []
        assert fetched.files_modified == []
        assert fetched.error_messages == []

    async def test_concurrent_writes(self, store: EpisodicStore) -> None:
        episodes = [_make_episode(task=f"concurrent task {i}") for i in range(20)]
        await asyncio.gather(*(store.store(ep) for ep in episodes))
        assert await store.count() == 20

    async def test_sql_injection_safe(self, store: EpisodicStore) -> None:
        malicious = "'; DROP TABLE episodes; --"
        episode = _make_episode(task=malicious)
        await store.store(episode)

        # Table must still exist and contain our row.
        fetched = await store.get_by_id(episode.id)
        assert fetched is not None
        assert fetched.task == malicious
        assert await store.count() == 1

    async def test_not_initialized_raises(self, tmp_path: Path) -> None:
        s = EpisodicStore(str(tmp_path / "uninit.db"))
        with pytest.raises(RuntimeError, match="not initialised"):
            await s.get_by_id("any-id")
