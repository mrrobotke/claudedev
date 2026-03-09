"""Tests for the orchestrator event dispatcher."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from claudedev.core.orchestrator import Orchestrator
from claudedev.core.state import IssueStatus


@pytest.fixture
def mock_settings() -> MagicMock:
    settings = MagicMock()
    settings.max_concurrent_sessions = 3
    settings.auto_enhance_issues = True
    settings.auto_implement = True
    settings.review_on_pr = True
    return settings


@pytest.fixture
def mock_gh_client() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def mock_claude_client() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def orchestrator(
    mock_settings: MagicMock,
    mock_gh_client: AsyncMock,
    mock_claude_client: AsyncMock,
) -> Orchestrator:
    return Orchestrator(
        settings=mock_settings,
        gh_client=mock_gh_client,
        claude_client=mock_claude_client,
    )


class TestDispatchImplement:
    async def test_dispatch_implement_creates_task(
        self,
        orchestrator: Orchestrator,
    ) -> None:
        task_key = orchestrator.dispatch_implement("owner/repo", 42)
        assert task_key is not None
        assert "implement:owner/repo#42" in task_key
        # Cancel background task to avoid event loop warnings
        for task in list(orchestrator._active_tasks.values()):
            task.cancel()

    async def test_dispatch_implement_idempotent(
        self,
        orchestrator: Orchestrator,
    ) -> None:
        first = orchestrator.dispatch_implement("owner/repo", 1)
        second = orchestrator.dispatch_implement("owner/repo", 1)
        assert first is not None
        assert second is None  # Already in progress
        for task in list(orchestrator._active_tasks.values()):
            task.cancel()


class TestImplementIssueCallsRunImplementation:
    async def test_implement_issue_calls_run_implementation(
        self,
        orchestrator: Orchestrator,
        seeded_db,
    ) -> None:
        """Verify _implement_issue delegates to team_engine.run_implementation (not spawn_team)."""
        from sqlalchemy import select

        from claudedev.core.state import Repo, TrackedIssue

        session = seeded_db
        result = await session.execute(select(Repo))
        repo = result.scalar_one()

        tracked = TrackedIssue(
            repo_id=repo.id,
            github_issue_number=5,
            status=IssueStatus.ENHANCED,
            tier="1",
            issue_metadata={"enhancement": "Some analysis"},
        )
        tracked.repo = repo
        session.add(tracked)
        await session.flush()
        await session.commit()

        run_impl_mock = AsyncMock(return_value=MagicMock())

        # Patch get_or_create_tracked_issue to return our tracked issue
        with (
            patch.object(
                orchestrator.issue_engine,
                "get_or_create_tracked_issue",
                new=AsyncMock(return_value=tracked),
            ),
            patch.object(
                orchestrator.team_engine,
                "run_implementation",
                new=run_impl_mock,
            ),
        ):
            await orchestrator._implement_issue("test/repo", 5, "implement:test/repo#5")

        run_impl_mock.assert_awaited_once()

    async def test_process_issue_calls_run_implementation_when_auto_implement(
        self,
        orchestrator: Orchestrator,
        seeded_db,
    ) -> None:
        """Verify _process_issue calls run_implementation (not spawn_team) when auto_implement."""
        from sqlalchemy import select

        from claudedev.core.state import Repo, TrackedIssue

        session = seeded_db
        result = await session.execute(select(Repo))
        repo = result.scalar_one()

        tracked = TrackedIssue(
            repo_id=repo.id,
            github_issue_number=6,
            status=IssueStatus.NEW,
            tier="2",
            issue_metadata={},
        )
        tracked.repo = repo
        session.add(tracked)
        await session.flush()
        await session.commit()

        enhance_mock = AsyncMock(return_value=tracked)
        run_impl_mock = AsyncMock(return_value=MagicMock())

        with (
            patch.object(
                orchestrator.issue_engine,
                "get_or_create_tracked_issue",
                new=AsyncMock(return_value=tracked),
            ),
            patch.object(orchestrator.issue_engine, "enhance_issue", new=enhance_mock),
            patch.object(orchestrator.team_engine, "run_implementation", new=run_impl_mock),
        ):
            await orchestrator._process_issue("test/repo", 6, "issue:test/repo#6")

        run_impl_mock.assert_awaited_once()
