"""Tests for the team implementation engine."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from claudedev.core.state import (
    IssueStatus,
    PRStatus,
    SessionStatus,
    TrackedIssue,
    TrackedPR,
)
from claudedev.engines.team_engine import TeamEngine


@pytest.fixture
def mock_settings() -> MagicMock:
    settings = MagicMock()
    settings.max_budget_per_issue = 5.0
    return settings


@pytest.fixture
def mock_gh_client() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def mock_claude_client() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def engine(
    mock_settings: MagicMock,
    mock_gh_client: AsyncMock,
    mock_claude_client: AsyncMock,
) -> TeamEngine:
    return TeamEngine(
        settings=mock_settings,
        gh_client=mock_gh_client,
        claude_client=mock_claude_client,
    )


class TestExtractPrNumber:
    def test_extracts_explicit_pr_number_line(self, engine: TeamEngine) -> None:
        text = "Some output.\n\nPR_NUMBER: 42\nBRANCH: claudedev/issue-1"
        assert TeamEngine._extract_pr_number(text) == 42

    def test_extracts_pr_number_case_insensitive(self, engine: TeamEngine) -> None:
        text = "pr_number: 99\n"
        assert TeamEngine._extract_pr_number(text) == 99

    def test_extracts_from_pull_request_mention(self, engine: TeamEngine) -> None:
        text = "Implementation complete. Created pull request #17 successfully."
        assert TeamEngine._extract_pr_number(text) == 17

    def test_extracts_from_pull_request_url(self, engine: TeamEngine) -> None:
        text = "See https://github.com/owner/repo/pull/55 for the PR."
        assert TeamEngine._extract_pr_number(text) == 55

    def test_prefers_explicit_line_over_url(self, engine: TeamEngine) -> None:
        text = "See https://github.com/owner/repo/pull/10\nPR_NUMBER: 20\n"
        assert TeamEngine._extract_pr_number(text) == 20

    def test_returns_none_when_no_pr(self, engine: TeamEngine) -> None:
        text = "Implementation complete. No PR was created."
        assert TeamEngine._extract_pr_number(text) is None

    def test_returns_none_for_empty_text(self, engine: TeamEngine) -> None:
        assert TeamEngine._extract_pr_number("") is None


class TestRunImplementation:
    async def test_run_implementation_with_pr(
        self,
        engine: TeamEngine,
        mock_gh_client: AsyncMock,
        mock_claude_client: AsyncMock,
        seeded_db,
    ) -> None:
        from sqlalchemy import select

        from claudedev.core.state import Repo

        session = seeded_db

        result = await session.execute(select(Repo))
        repo = result.scalar_one()

        tracked = TrackedIssue(
            repo_id=repo.id,
            github_issue_number=10,
            tier="1",
            issue_metadata={"enhancement": "Fix the login redirect bug."},
        )
        tracked.repo = repo
        session.add(tracked)
        await session.flush()

        mock_gh_issue = MagicMock()
        mock_gh_issue.title = "Fix login redirect"
        mock_gh_client.get_issue_full_context = AsyncMock(return_value=(mock_gh_issue, [], []))
        mock_gh_client.comment_on_issue = AsyncMock()

        implementation_output = (
            "Implementation done. Created pull request #7.\n"
            "\n"
            "PR_NUMBER: 7\n"
            "BRANCH: claudedev/issue-10\n"
        )

        async def mock_run_query(prompt: str, **kwargs):  # type: ignore[no-untyped-def]
            for chunk in [implementation_output]:
                yield chunk

        mock_claude_client.run_query = mock_run_query

        with (
            patch.object(engine, "_find_claude_session_id", return_value="test-session-id"),
            patch("claudedev.engines.team_engine.WorktreeManager") as mock_wt_cls,
        ):
            mock_wt = mock_wt_cls.return_value
            mock_wt.create_worktree = AsyncMock(
                return_value=MagicMock(path=Path("/tmp/wt/issue-10"))
            )
            mock_wt.write_hook_config = AsyncMock()
            agent_session = await engine.run_implementation(session, tracked)

        assert agent_session.status == SessionStatus.COMPLETED
        assert agent_session.claude_session_id == "test-session-id"
        assert tracked.pr_number == 7
        assert tracked.status == IssueStatus.IN_REVIEW

        mock_gh_client.comment_on_issue.assert_awaited_once()
        comment_args = mock_gh_client.comment_on_issue.call_args
        assert "#7" in comment_args[0][2] or "#7" in str(comment_args)

    async def test_run_implementation_creates_tracked_pr(
        self,
        engine: TeamEngine,
        mock_gh_client: AsyncMock,
        mock_claude_client: AsyncMock,
        seeded_db,
    ) -> None:
        """When a PR is found, a TrackedPR record is created in the database."""
        from sqlalchemy import select

        from claudedev.core.state import Repo

        session = seeded_db

        result = await session.execute(select(Repo))
        repo = result.scalar_one()

        tracked = TrackedIssue(
            repo_id=repo.id,
            github_issue_number=11,
            tier="1",
            issue_metadata={"enhancement": "Add feature X."},
        )
        tracked.repo = repo
        session.add(tracked)
        await session.flush()

        mock_gh_issue = MagicMock()
        mock_gh_issue.title = "Add feature X"
        mock_gh_client.get_issue_full_context = AsyncMock(return_value=(mock_gh_issue, [], []))
        mock_gh_client.comment_on_issue = AsyncMock()

        async def mock_run_query(prompt: str, **kwargs):  # type: ignore[no-untyped-def]
            yield "PR_NUMBER: 15\nBRANCH: claudedev/issue-11\n"

        mock_claude_client.run_query = mock_run_query

        with (
            patch.object(engine, "_find_claude_session_id", return_value=None),
            patch("claudedev.engines.team_engine.WorktreeManager") as mock_wt_cls,
        ):
            mock_wt = mock_wt_cls.return_value
            mock_wt.create_worktree = AsyncMock(
                return_value=MagicMock(path=Path("/tmp/wt/issue-11"))
            )
            mock_wt.write_hook_config = AsyncMock()
            await engine.run_implementation(session, tracked)

        # Verify TrackedPR was created
        pr_result = await session.execute(select(TrackedPR).where(TrackedPR.pr_number == 15))
        tracked_pr = pr_result.scalar_one()
        assert tracked_pr.issue_id == tracked.id
        assert tracked_pr.repo_id == repo.id
        assert tracked_pr.status == PRStatus.OPEN
        assert tracked_pr.review_iteration == 0

    async def test_run_implementation_without_pr(
        self,
        engine: TeamEngine,
        mock_gh_client: AsyncMock,
        mock_claude_client: AsyncMock,
        seeded_db,
    ) -> None:
        from sqlalchemy import select

        from claudedev.core.state import Repo

        session = seeded_db

        result = await session.execute(select(Repo))
        repo = result.scalar_one()

        tracked = TrackedIssue(
            repo_id=repo.id,
            github_issue_number=20,
            tier="1",
            issue_metadata={"enhancement": "Small fix."},
        )
        tracked.repo = repo
        session.add(tracked)
        await session.flush()

        mock_gh_issue = MagicMock()
        mock_gh_issue.title = "Small typo fix"
        mock_gh_client.get_issue_full_context = AsyncMock(return_value=(mock_gh_issue, [], []))
        mock_gh_client.comment_on_issue = AsyncMock()
        # Branch-based fallback also finds no PR in this scenario
        mock_gh_client.find_pr_by_branch = AsyncMock(return_value=None)

        # Output with no PR number
        implementation_output = "Committed the fix directly to main. No PR needed.\n"

        async def mock_run_query(prompt: str, **kwargs):  # type: ignore[no-untyped-def]
            for chunk in [implementation_output]:
                yield chunk

        mock_claude_client.run_query = mock_run_query

        with (
            patch.object(engine, "_find_claude_session_id", return_value=None),
            patch("claudedev.engines.team_engine.WorktreeManager") as mock_wt_cls,
        ):
            mock_wt = mock_wt_cls.return_value
            mock_wt.create_worktree = AsyncMock(
                return_value=MagicMock(path=Path("/tmp/wt/issue-20"))
            )
            mock_wt.write_hook_config = AsyncMock()
            agent_session = await engine.run_implementation(session, tracked)

        assert agent_session.status == SessionStatus.COMPLETED
        assert tracked.pr_number is None
        assert tracked.status == IssueStatus.DONE
        # No comment posted when no PR
        mock_gh_client.comment_on_issue.assert_not_awaited()
        # Branch fallback was tried with the correct repo and branch name
        mock_gh_client.find_pr_by_branch.assert_awaited_once_with("test/repo", "claudedev/issue-20")

        # No TrackedPR should have been created
        pr_result = await session.execute(select(TrackedPR).where(TrackedPR.issue_id == tracked.id))
        assert pr_result.scalar_one_or_none() is None

    async def test_run_implementation_failure_sets_failed_status(
        self,
        engine: TeamEngine,
        mock_gh_client: AsyncMock,
        mock_claude_client: AsyncMock,
        seeded_db,
    ) -> None:
        from sqlalchemy import select

        from claudedev.core.state import Repo

        session = seeded_db

        result = await session.execute(select(Repo))
        repo = result.scalar_one()

        tracked = TrackedIssue(
            repo_id=repo.id,
            github_issue_number=30,
            tier="2",
            issue_metadata={"enhancement": "Some enhancement."},
        )
        tracked.repo = repo
        session.add(tracked)
        await session.flush()
        # Simulate enhanced status
        tracked.status = IssueStatus.ENHANCED

        mock_gh_client.get_issue_full_context = AsyncMock(
            side_effect=RuntimeError("GitHub API error")
        )

        with pytest.raises(RuntimeError, match="GitHub API error"):
            await engine.run_implementation(session, tracked)

        assert tracked.status == IssueStatus.FAILED
        assert tracked.implementation_started_at is None

    async def test_run_implementation_worktree_fallback(
        self,
        engine: TeamEngine,
        mock_gh_client: AsyncMock,
        mock_claude_client: AsyncMock,
        seeded_db,
    ) -> None:
        """When worktree creation fails, falls back to repo.local_path."""
        from sqlalchemy import select

        from claudedev.core.state import Repo

        session = seeded_db

        result = await session.execute(select(Repo))
        repo = result.scalar_one()

        tracked = TrackedIssue(
            repo_id=repo.id,
            github_issue_number=40,
            tier="1",
            issue_metadata={"enhancement": "Some work."},
        )
        tracked.repo = repo
        session.add(tracked)
        await session.flush()

        mock_gh_issue = MagicMock()
        mock_gh_issue.title = "Some work"
        mock_gh_client.get_issue_full_context = AsyncMock(return_value=(mock_gh_issue, [], []))
        mock_gh_client.comment_on_issue = AsyncMock()
        mock_gh_client.find_pr_by_branch = AsyncMock(return_value=None)

        captured_cwd = {}

        async def mock_run_query(prompt: str, **kwargs):  # type: ignore[no-untyped-def]
            captured_cwd["cwd"] = kwargs.get("cwd")
            yield "Done. No PR needed.\n"

        mock_claude_client.run_query = mock_run_query

        with (
            patch.object(engine, "_find_claude_session_id", return_value=None),
            patch("claudedev.engines.team_engine.WorktreeManager") as mock_wt_cls,
        ):
            mock_wt = mock_wt_cls.return_value
            mock_wt.create_worktree = AsyncMock(side_effect=RuntimeError("git worktree failed"))
            await engine.run_implementation(session, tracked)

        # Should have fallen back to repo.local_path
        assert captured_cwd["cwd"] == repo.local_path
        assert tracked.worktree_path is None

    async def test_run_implementation_uses_worktree_path(
        self,
        engine: TeamEngine,
        mock_gh_client: AsyncMock,
        mock_claude_client: AsyncMock,
        seeded_db,
    ) -> None:
        """When worktree creation succeeds, run_query uses the worktree path."""
        from sqlalchemy import select

        from claudedev.core.state import Repo

        session = seeded_db

        result = await session.execute(select(Repo))
        repo = result.scalar_one()

        tracked = TrackedIssue(
            repo_id=repo.id,
            github_issue_number=50,
            tier="1",
            issue_metadata={"enhancement": "Build feature."},
        )
        tracked.repo = repo
        session.add(tracked)
        await session.flush()

        mock_gh_issue = MagicMock()
        mock_gh_issue.title = "Build feature"
        mock_gh_client.get_issue_full_context = AsyncMock(return_value=(mock_gh_issue, [], []))
        mock_gh_client.comment_on_issue = AsyncMock()
        mock_gh_client.find_pr_by_branch = AsyncMock(return_value=None)

        captured_cwd = {}

        async def mock_run_query(prompt: str, **kwargs):  # type: ignore[no-untyped-def]
            captured_cwd["cwd"] = kwargs.get("cwd")
            yield "Done. No PR needed.\n"

        mock_claude_client.run_query = mock_run_query

        worktree_path = Path("/tmp/wt/issue-50")

        with (
            patch.object(engine, "_find_claude_session_id", return_value=None),
            patch("claudedev.engines.team_engine.WorktreeManager") as mock_wt_cls,
        ):
            mock_wt = mock_wt_cls.return_value
            mock_wt.create_worktree = AsyncMock(return_value=MagicMock(path=worktree_path))
            mock_wt.write_hook_config = AsyncMock()
            await engine.run_implementation(session, tracked)

        # Should have used worktree path
        assert captured_cwd["cwd"] == str(worktree_path)
        assert tracked.worktree_path == str(worktree_path)
        # Hook config should have been written
        mock_wt.write_hook_config.assert_awaited_once()


class TestWorktreeIntegration:
    async def test_worktree_path_format(self) -> None:
        from claudedev.engines.worktree_manager import WorktreeManager

        wt = WorktreeManager()
        path = wt.get_worktree_path(Path("/repo"), 42)
        assert ".claudedev/worktrees/issue-42" in str(path)


class TestPREnforcement:
    async def test_extract_pr_number_from_metadata(self) -> None:
        text = "Implementation done\nPR_NUMBER: 15\nBRANCH: claudedev/issue-42"
        result = TeamEngine._extract_pr_number(text)
        assert result == 15

    async def test_extract_pr_number_from_url(self) -> None:
        text = "Created https://github.com/owner/repo/pull/23"
        result = TeamEngine._extract_pr_number(text)
        assert result == 23

    async def test_extract_pr_number_none(self) -> None:
        text = "Done with implementation, no PR created."
        result = TeamEngine._extract_pr_number(text)
        assert result is None
